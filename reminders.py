"""
Напоминания «пора поесть» по недобору КБЖУ. Проверка каждые 15 минут.
Напоминание приходит, когда прошло достаточно времени после последнего приёма (45/90/120 мин)
и есть недобор по целям. Не слать ночью (до 8:00 и после 22:00).
"""
import asyncio
import logging
from datetime import datetime

from database import (
    get_users_for_reminders,
    get_user,
    get_daily_totals,
    get_meals_today,
    get_last_meal_today,
    get_reminder_count_today,
    get_last_reminder_sent_at,
    log_reminder_sent,
)
from gemini_helper import get_reminder_suggestion

logger = logging.getLogger("reminders")

# Не слать до этого часа и после CUTOFF_HOUR (по серверному времени)
START_HOUR = 8
CUTOFF_HOUR = 22
# Минимальный интервал (мин) между двумя напоминаниями одному пользователю
MIN_MINUTES_BETWEEN_REMINDERS = 90
# Минимальный недобор для напоминания (калории, белок г, углеводы г)
MIN_SHORTFALL_CAL = 50
MIN_SHORTFALL_PROT = 8
MIN_SHORTFALL_CARB = 15

# Минимальный интервал (мин) после последнего приёма перед напоминанием: от калорийности приёма
# перекус (~до 200 ккал) — 45 мин, средний приём (200–450) — 90 мин, плотный — 120 мин
def _min_minutes_after_last_meal(last_meal_calories: int) -> int:
    if last_meal_calories < 200:
        return 45
    if last_meal_calories < 450:
        return 90
    return 120


async def run_reminders(bot):
    """Для пользователей с недобором и включёнными напоминаниями — отправить совет, если прошло достаточно времени после последнего приёма."""
    now = datetime.now()
    if now.hour < START_HOUR or now.hour >= CUTOFF_HOUR:
        return
    for user_id in await get_users_for_reminders():
        try:
            user = await get_user(user_id)
            if not user:
                continue
            if user.get("reminders_enabled") == 0:
                continue
            per_day = user.get("reminders_per_day") or 3
            if await get_reminder_count_today(user_id) >= per_day:
                continue
            last_sent = await get_last_reminder_sent_at(user_id)
            if last_sent is not None:
                mins_since = int((now - last_sent).total_seconds() / 60)
                if mins_since < MIN_MINUTES_BETWEEN_REMINDERS:
                    continue
            totals = await get_daily_totals(user_id)
            cal_goal = user.get("calories_goal") or 0
            prot_goal = user.get("protein_goal") or 0
            carb_goal = user.get("carbs_goal") or 0
            if not cal_goal:
                continue
            cal_rem = cal_goal - totals["calories"]
            prot_rem = prot_goal - totals["protein"]
            carb_rem = carb_goal - totals["carbs"]
            if cal_rem < MIN_SHORTFALL_CAL and prot_rem < MIN_SHORTFALL_PROT and carb_rem < MIN_SHORTFALL_CARB:
                continue
            meals_today = await get_meals_today(user_id)
            eaten = [m[1] for m in meals_today]

            last_meal = await get_last_meal_today(user_id)
            last_meal_minutes_ago = None
            last_meal_name = None
            if last_meal:
                created_at_str, last_meal_name, last_cal = last_meal[0], last_meal[1], int(last_meal[2] or 0)
                try:
                    last_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00").split("+")[0].strip())
                    if last_dt.tzinfo:
                        last_dt = last_dt.replace(tzinfo=None)
                    last_meal_minutes_ago = int((now - last_dt).total_seconds() / 60)
                    min_interval = _min_minutes_after_last_meal(last_cal)
                    if last_meal_minutes_ago < min_interval:
                        continue
                except (ValueError, TypeError):
                    last_meal_minutes_ago = None
                    last_meal_name = None

            text = get_reminder_suggestion(
                totals, user, eaten, now.hour,
                last_meal_minutes_ago=last_meal_minutes_ago,
                last_meal_name=last_meal_name,
            )
            if not text:
                continue
            await bot.send_message(user_id, "🔔 " + text)
            await log_reminder_sent(user_id)
            logger.info("Reminder sent to user_id=%s", user_id)
        except Exception as e:
            logger.exception("Reminder for user_id=%s: %s", user_id, e)


async def reminder_loop(bot):
    """Каждые 15 минут проверять, не пора ли отправить напоминания."""
    while True:
        await asyncio.sleep(60 * 15)
        await run_reminders(bot)

"""
Напоминания «пора поесть» по недобору КБЖУ. Запускаются в слоты 10:00, 14:00, 18:00, 20:00.
После 22:00 не отправляем. Учитываются цели, сегодняшний рацион и время последнего приёма:
лёгкий перекус — можно напомнить раньше, плотный приём — позже.
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
    log_reminder_sent,
)
from gemini_helper import get_reminder_suggestion

logger = logging.getLogger("reminders")

# Часы, когда разрешено слать напоминания (по серверному времени)
REMINDER_HOURS = (10, 14, 18, 20)
# Не слать после этого часа
CUTOFF_HOUR = 22
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
    """Проверить время, для пользователей с недобором и включёнными напоминаниями — отправить совет."""
    now = datetime.now()
    # Запуск только в начале слота (раз в час), чтобы не слать дважды за час
    if now.hour not in REMINDER_HOURS or now.minute >= 15:
        return
    for user_id in get_users_for_reminders():
        try:
            user = get_user(user_id)
            if not user:
                continue
            if user.get("reminders_enabled") == 0:
                continue
            per_day = user.get("reminders_per_day") or 3
            if get_reminder_count_today(user_id) >= per_day:
                continue
            if now.hour >= CUTOFF_HOUR:
                continue
            totals = get_daily_totals(user_id)
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
            meals_today = get_meals_today(user_id)
            eaten = [m[1] for m in meals_today]

            last_meal = get_last_meal_today(user_id)
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
            log_reminder_sent(user_id)
            logger.info("Reminder sent to user_id=%s", user_id)
        except Exception as e:
            logger.exception("Reminder for user_id=%s: %s", user_id, e)


async def reminder_loop(bot):
    """Каждые 15 минут проверять, не пора ли отправить напоминания."""
    while True:
        await asyncio.sleep(60 * 15)
        await run_reminders(bot)

"""
Напоминания «пора поесть» по недобору КБЖУ. Запускаются в слоты 10:00, 14:00, 18:00, 20:00.
После 22:00 не отправляем. Учитываются цели пользователя и уже съеденное за день.
"""
import asyncio
import logging
from datetime import datetime

from database import (
    get_users_for_reminders,
    get_user,
    get_daily_totals,
    get_meals_today,
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
            text = get_reminder_suggestion(totals, user, eaten, now.hour)
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

"""
Напоминания «пора поесть» по недобору КБЖУ. Проверка каждые 15 минут.
Напоминание приходит, когда прошло достаточно времени после последнего приёма (45/90/120 мин)
и есть недобор по целям. Не слать ночью (до 8:00 и после 22:00).
Дополнительно: уведомления о достижении целей за день и мягкий AI-комментарий при 5 днях подряд недобора/перебора.
"""
import asyncio
import logging
from datetime import datetime, date, timedelta

from database import (
    get_users_for_reminders,
    get_users_for_reengage,
    get_user,
    get_daily_totals,
    get_meals_today,
    get_last_meal_today,
    get_reminder_count_today,
    get_last_reminder_sent_at,
    log_reminder_sent,
    was_notification_sent,
    log_notification_sent,
    get_last_streak_notification_date,
    get_last_reengage_sent_at,
    log_reengage_sent,
)
from gemini_helper import get_reminder_suggestion, get_goal_reached_message, get_5day_streak_message
from week_status import run_week_status

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


# Пороги для 5-дневных серий: недобор белка < 85% цели, перебор жиров/калорий > 110%
PROTEIN_SHORTFALL_PCT = 0.85
FAT_CAL_OVER_PCT = 1.10

# Reengage: через сколько часов неактивности слать напоминание
REENGAGE_HOURS_48 = 48
REENGAGE_HOURS_5D = 4 * 24  # 96 часов = 4 дня (слать при 4–5 днях тишины)
REENGAGE_MIN_HOURS_SINCE_48H_SENT = 48
REENGAGE_MIN_DAYS_SINCE_5D_SENT = 5

REENGAGE_MSG_48H = "Я тебя потерял 👀\n\nПродолжаем следить за прогрессом?"
REENGAGE_MSG_5D = "Даже 1 пропущенный день может сбить ритм.\n\nЗаймёт 30 секунд — просто добавь последний приём пищи."


async def check_goal_reached_and_send(user_id: int, bot):
    """
    Если пользователь достиг цели за день (белок / калории / все цели) — отправить поздравление и мотивирующее сообщение (раз в день на цель).
    Вызывается после добавления еды и из run_reminders.
    Не шлёт, если у пользователя выключены уведомления «О прогрессе».
    """
    today = date.today()
    user = await get_user(user_id)
    if not user:
        return
    if user.get("progress_notifications_enabled") == 0:
        return
    totals = await get_daily_totals(user_id, today)
    prot_goal = user.get("protein_goal") or 0
    cal_goal = user.get("calories_goal") or 0
    fat_goal = user.get("fat_goal") or 0
    carb_goal = user.get("carbs_goal") or 0

    # Цель по белку
    if prot_goal and totals["protein"] >= prot_goal:
        if not await was_notification_sent(user_id, today, "protein_goal"):
            data = get_goal_reached_message("protein", user, totals)
            if data and data.get("benefit"):
                fact = f"Сегодня ты закрыл норму белка — {totals['protein']:.0f} г из {prot_goal} г"
                text = f"🎯 {fact}\n\n💪 {data['benefit']}"
                if data.get("motivation"):
                    text += f"\n\n🔥 {data['motivation']}"
                try:
                    await bot.send_message(user_id, text)
                    await log_notification_sent(user_id, today, "protein_goal")
                    logger.info("Goal reached (protein) sent to user_id=%s", user_id)
                except Exception as e:
                    logger.exception("Send goal_reached protein: %s", e)

    # Цель по калориям
    if cal_goal and totals["calories"] >= cal_goal:
        if not await was_notification_sent(user_id, today, "calories_goal"):
            data = get_goal_reached_message("calories", user, totals)
            if data and data.get("benefit"):
                fact = f"Сегодня ты закрыл норму калорий — {totals['calories']} ккал из {cal_goal} ккал"
                text = f"🎯 {fact}\n\n💪 {data['benefit']}"
                if data.get("motivation"):
                    text += f"\n\n🔥 {data['motivation']}"
                try:
                    await bot.send_message(user_id, text)
                    await log_notification_sent(user_id, today, "calories_goal")
                    logger.info("Goal reached (calories) sent to user_id=%s", user_id)
                except Exception as e:
                    logger.exception("Send goal_reached calories: %s", e)

    # Все цели (белок, калории, жиры, углеводы)
    if prot_goal and cal_goal and fat_goal and carb_goal:
        if totals["protein"] >= prot_goal and totals["calories"] >= cal_goal and totals["fat"] >= fat_goal and totals["carbs"] >= carb_goal:
            if not await was_notification_sent(user_id, today, "full_goal"):
                data = get_goal_reached_message("full", user, totals)
                if data and data.get("benefit"):
                    fact = f"Сегодня ты выполнил все дневные цели: калории {totals['calories']}/{cal_goal}, белок {totals['protein']:.0f}/{prot_goal} г, жиры {totals['fat']:.0f}/{fat_goal} г, углеводы {totals['carbs']:.0f}/{carb_goal} г"
                    text = f"🎯 {fact}\n\n💪 {data['benefit']}"
                    if data.get("motivation"):
                        text += f"\n\n🔥 {data['motivation']}"
                    try:
                        await bot.send_message(user_id, text)
                        await log_notification_sent(user_id, today, "full_goal")
                        logger.info("Goal reached (full) sent to user_id=%s", user_id)
                    except Exception as e:
                        logger.exception("Send goal_reached full: %s", e)


async def _get_5day_summary(user_id: int, user: dict) -> list:
    today = date.today()
    goals = {
        "calories_goal": user.get("calories_goal") or 0,
        "protein_goal": user.get("protein_goal") or 0,
        "fat_goal": user.get("fat_goal") or 0,
        "carbs_goal": user.get("carbs_goal") or 0,
    }
    out = []
    for i in range(5):
        d = today - timedelta(days=i)
        totals = await get_daily_totals(user_id, d)
        out.append({
            "date": d.isoformat(),
            "totals": totals,
            "goals": goals,
        })
    return out


async def check_5day_streak_and_send(user_id: int, bot):
    """
    Если 5 дней подряд: недобор белка (< 85% цели) или перебор жиров/калорий (> 110%) — отправить мягкий AI-комментарий (раз на серию).
    Запускаем вечером (с 19:00), чтобы не слать утром.
    Не шлёт, если у пользователя выключены уведомления «О прогрессе».
    """
    now = datetime.now()
    if now.hour < 19:
        return
    today = date.today()
    user = await get_user(user_id)
    if not user:
        return
    if user.get("progress_notifications_enabled") == 0:
        return
    prot_goal = user.get("protein_goal") or 0
    fat_goal = user.get("fat_goal") or 0
    cal_goal = user.get("calories_goal") or 0
    if not prot_goal and not fat_goal and not cal_goal:
        return

    summary = await _get_5day_summary(user_id, user)
    if len(summary) < 5:
        return

    def protein_bad(s):
        g = s["goals"].get("protein_goal") or 0
        return g > 0 and (s["totals"]["protein"] or 0) < PROTEIN_SHORTFALL_PCT * g

    def fat_bad(s):
        g = s["goals"].get("fat_goal") or 0
        return g > 0 and (s["totals"]["fat"] or 0) > FAT_CAL_OVER_PCT * g

    def cal_bad(s):
        g = s["goals"].get("calories_goal") or 0
        return g > 0 and (s["totals"]["calories"] or 0) > FAT_CAL_OVER_PCT * g

    streak_protein = all(protein_bad(s) for s in summary)
    streak_fat = all(fat_bad(s) for s in summary)
    streak_cal = all(cal_bad(s) for s in summary)

    for streak_type, key, cond in [
        ("protein_shortfall", "5day_protein", streak_protein),
        ("fat_over", "5day_fat", streak_fat),
        ("cal_over", "5day_cal", streak_cal),
    ]:
        if not cond:
            continue
        last_sent = await get_last_streak_notification_date(user_id, key)
        if last_sent is not None and (today - last_sent).days < 5:
            continue
        msg = get_5day_streak_message(streak_type, user, summary)
        if not msg:
            continue
        try:
            await bot.send_message(user_id, "💬 " + msg)
            await log_notification_sent(user_id, today, key)
            logger.info("5day_streak %s sent to user_id=%s", key, user_id)
        except Exception as e:
            logger.exception("Send 5day_streak: %s", e)
        break


async def run_reengage_reminders(bot):
    """
    Напоминания «вернись» при долгой неактивности (как в Lingualeo).
    - Через 48 ч без взаимодействия — мягкое: «Я тебя потерял 👀 Продолжаем следить за прогрессом?»
    - Через 4–5 дней тишины — мотивирующее: «Даже 1 пропущенный день может сбить ритм. Займёт 30 секунд...»
    """
    now = datetime.now()
    for user_id in await get_users_for_reengage():
        try:
            user = await get_user(user_id)
            if not user:
                continue
            last_activity = user.get("last_activity_at")
            if last_activity is None:
                last_activity = user.get("created_at")
            if last_activity is None:
                continue
            if getattr(last_activity, "tzinfo", None):
                last_activity = last_activity.replace(tzinfo=None)
            hours_inactive = (now - last_activity).total_seconds() / 3600

            # Сначала проверяем 4–5 дней: более сильное сообщение
            if hours_inactive >= REENGAGE_HOURS_5D:
                last_sent = await get_last_reengage_sent_at(user_id, "reengage_5d")
                if last_sent is None or (now - last_sent).days >= REENGAGE_MIN_DAYS_SINCE_5D_SENT:
                    await bot.send_message(user_id, "👋 " + REENGAGE_MSG_5D)
                    await log_reengage_sent(user_id, "reengage_5d")
                    logger.info("Reengage 5d sent to user_id=%s", user_id)
                    continue

            # Иначе через 48 ч — мягкое
            if hours_inactive >= REENGAGE_HOURS_48:
                last_sent = await get_last_reengage_sent_at(user_id, "reengage_48h")
                if last_sent is None or (now - last_sent).total_seconds() / 3600 >= REENGAGE_MIN_HOURS_SINCE_48H_SENT:
                    await bot.send_message(user_id, "👋 " + REENGAGE_MSG_48H)
                    await log_reengage_sent(user_id, "reengage_48h")
                    logger.info("Reengage 48h sent to user_id=%s", user_id)
        except Exception as e:
            logger.exception("Reengage for user_id=%s: %s", user_id, e)


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
            # Проверка достижения целей за день (поздравление + мотивация)
            await check_goal_reached_and_send(user_id, bot)
            # Проверка 5 дней подряд недобор/перебор — мягкий AI-комментарий (вечером)
            await check_5day_streak_and_send(user_id, bot)
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


async def run_midnight_today_update(bot):
    """
    В 00:00 (по серверному времени) отправить каждому пользователю с целями сообщение о новом дне —
    «обновление» статистики «Сегодня»: цели на день, призыв к учёту.
    """
    now = datetime.now()
    if now.hour != 0:
        return
    today = date.today()
    for user_id in await get_users_for_reminders():
        try:
            if await was_notification_sent(user_id, today, "midnight_today_refresh"):
                continue
            user = await get_user(user_id)
            if not user or not user.get("calories_goal"):
                continue
            cal = user.get("calories_goal") or 0
            prot = user.get("protein_goal") or 0
            fat = user.get("fat_goal") or 0
            carb = user.get("carbs_goal") or 0
            text = (
                "🌅 <b>Новый день!</b>\n\n"
                f"Статистика «Сегодня» обновлена. Цели на сегодня:\n"
                f"🔥 {cal} ккал · 🥩 {prot} г · 🧈 {fat} г · 🍞 {carb} г\n\n"
                "Удачи! 🍽"
            )
            await bot.send_message(user_id, text, parse_mode="HTML")
            await log_notification_sent(user_id, today, "midnight_today_refresh")
            logger.info("Midnight today update sent to user_id=%s", user_id)
        except Exception as e:
            logger.exception("Midnight update for user_id=%s: %s", user_id, e)


async def reminder_loop(bot):
    """Каждые 15 минут: напоминания по недобору, reengage при долгой неактивности, в 00:00 — обновление «Сегодня», в 19:00 раз в 7 дней — Статус недели."""
    while True:
        await asyncio.sleep(60 * 15)
        await run_midnight_today_update(bot)
        await run_reminders(bot)
        await run_reengage_reminders(bot)
        await run_week_status(bot)

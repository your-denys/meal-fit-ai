"""
Статус недели: раз в 7 дней с момента старта пользователя, в 19:00.
Если в неделе ≥3 дней с данными — отправляем отчёт (баланс / перегруз / агрессивный дефицит).
Если <3 дней — скипаем неделю, ничего не шлём.
"""
import logging
from datetime import date, datetime, timedelta

from database import (
    get_users_for_reminders,
    get_user,
    get_meals_range,
    was_notification_sent,
    log_notification_sent,
)
from gemini_helper import get_week_status_recommendation

logger = logging.getLogger("week_status")

MIN_DAYS_WITH_DATA = 3
WEEK_STATUS_HOUR = 19

# Логика статусов (цель — похудение/сушка)
DEFICIT_BALANCE_MIN = 200
DEFICIT_BALANCE_MAX = 500
DEFICIT_AGGRESSIVE = 700
PROTEIN_DAYS_BALANCE_MIN = 5  # ≥70% из 7
OVERLOAD_DAYS_SURPLUS = 3
OVERLOAD_CAL_OVER_PCT = 15
OVERLOAD_FAT_DAYS = 4
UNDER_70_DAYS = 3


def _user_start_date(user: dict) -> date | None:
    created = user.get("created_at")
    if not created:
        return None
    if hasattr(created, "date"):
        return created.date()
    try:
        return date.fromisoformat(str(created)[:10])
    except (ValueError, TypeError):
        return None


def _compute_week_stats(rows: list, cal_goal: int, prot_goal: float, fat_goal: float) -> dict:
    """rows из get_meals_range: (date_str, cal, prot, fat, carb) по дням."""
    n_days = 7
    total_cal = sum(r[1] for r in rows)
    total_prot = sum(r[2] for r in rows)
    total_fat = sum(r[3] for r in rows)
    days_with_data = len(rows)
    days_surplus = sum(1 for r in rows if cal_goal and (r[1] or 0) > cal_goal)
    days_cal_over_15 = sum(1 for r in rows if cal_goal and (r[1] or 0) > cal_goal * 1.15)
    days_fat_over = sum(1 for r in rows if fat_goal and (r[3] or 0) > fat_goal)
    days_under_70 = sum(1 for r in rows if cal_goal and (r[1] or 0) < cal_goal * 0.70)
    protein_days_met = sum(1 for r in rows if prot_goal and (r[2] or 0) >= prot_goal)

    avg_cal = total_cal / n_days if n_days else 0
    avg_deficit = (cal_goal - avg_cal) if cal_goal else 0
    calorie_adherence_pct = (total_cal / (n_days * cal_goal) * 100) if cal_goal and n_days else 0

    return {
        "avg_deficit": avg_deficit,
        "calorie_adherence_pct": calorie_adherence_pct,
        "protein_days_met": protein_days_met,
        "days_with_data": days_with_data,
        "days_surplus": days_surplus,
        "days_cal_over_15": days_cal_over_15,
        "days_fat_over": days_fat_over,
        "days_under_70": days_under_70,
    }


def _determine_status(goal: str, stats: dict) -> tuple[str, str]:
    """Возвращает (status_key, emoji_label)."""
    g = goal or "maintain"
    d = stats["avg_deficit"]
    prot_met = stats["protein_days_met"]
    surplus = stats["days_surplus"]
    cal_over = stats["days_cal_over_15"]
    fat_over = stats["days_fat_over"]
    under_70 = stats["days_under_70"]

    if g == "gain":
        if surplus >= OVERLOAD_DAYS_SURPLUS or (stats["calorie_adherence_pct"] > 100 + OVERLOAD_CAL_OVER_PCT):
            return "overload", "Перегруз 🟡"
        if d > DEFICIT_AGGRESSIVE or under_70 >= UNDER_70_DAYS:
            return "aggressive_deficit", "Дефицит слишком высокий 🔴"
        return "balance", "Баланс 🟢"

    if g in ("maintain", "recomp"):
        if surplus >= OVERLOAD_DAYS_SURPLUS or fat_over >= OVERLOAD_FAT_DAYS:
            return "overload", "Перегруз 🟡"
        if abs(d) <= DEFICIT_BALANCE_MAX and prot_met >= PROTEIN_DAYS_BALANCE_MIN:
            return "balance", "Баланс 🟢"
        return "balance", "Баланс 🟢"

    if surplus >= OVERLOAD_DAYS_SURPLUS or cal_over >= 3 or fat_over >= OVERLOAD_FAT_DAYS:
        return "overload", "Перегруз 🟡"
    if d > DEFICIT_AGGRESSIVE or under_70 >= UNDER_70_DAYS:
        return "aggressive_deficit", "Дефицит слишком высокий 🔴"
    if DEFICIT_BALANCE_MIN <= d <= DEFICIT_BALANCE_MAX and prot_met >= PROTEIN_DAYS_BALANCE_MIN and cal_over == 0:
        return "balance", "Баланс 🟢"
    if d < 0 and g in ("loss", "cutting"):
        return "overload", "Перегруз 🟡"
    return "balance", "Баланс 🟢"


def _index_from_stats(stats: dict, status_key: str) -> int:
    """Индекс недели 0–100."""
    adh = min(100, max(0, stats["calorie_adherence_pct"]))
    prot_score = (stats["protein_days_met"] / 7) * 100
    if status_key == "balance":
        return int(adh * 0.5 + prot_score * 0.5)
    if status_key == "overload":
        return max(0, int(70 - (stats["days_surplus"] * 10 + stats["days_fat_over"] * 5)))
    return max(0, min(100, int(adh + prot_score) // 2))


def _index_label(pct: int) -> str:
    if pct >= 80:
        return "Отличная неделя"
    if pct >= 60:
        return "Есть зоны роста"
    if pct >= 40:
        return "Нестабильный режим"
    return "Стоит скорректировать план"


async def run_week_status(bot):
    """
    Раз в 7 дней с момента старта пользователя, в 19:00.
    Если сегодня — последний день недели (по циклу от created_at) и в неделе ≥3 дней с данными,
    отправляем «Статус недели». Иначе скипаем.
    """
    now = datetime.now()
    if now.hour != WEEK_STATUS_HOUR:
        return
    today = date.today()
    for user_id in await get_users_for_reminders():
        try:
            user = await get_user(user_id)
            if not user or user.get("week_status_enabled") == 0:
                continue
            if not user.get("calories_goal") or not user.get("protein_goal"):
                continue
            start_date = _user_start_date(user)
            if not start_date:
                continue
            days_since_start = (today - start_date).days
            if days_since_start < 6:
                continue
            if (days_since_start % 7) != 6:
                continue
            if await was_notification_sent(user_id, today, "week_status"):
                continue
            from_date = today - timedelta(days=6)
            to_date = today
            rows = await get_meals_range(user_id, from_date, to_date)
            if len(rows) < MIN_DAYS_WITH_DATA:
                continue
            cal_goal = user.get("calories_goal") or 0
            prot_goal = float(user.get("protein_goal") or 0)
            fat_goal = float(user.get("fat_goal") or 0)
            stats = _compute_week_stats(rows, cal_goal, prot_goal, fat_goal)
            status_key, status_label = _determine_status(user.get("goal", ""), stats)
            index_pct = _index_from_stats(stats, status_key)
            index_label = _index_label(index_pct)
            rec = get_week_status_recommendation(
                status_key,
                user.get("goal", ""),
                stats["avg_deficit"],
                stats["calorie_adherence_pct"],
                stats["protein_days_met"],
                index_pct,
            )
            deficit_str = f"{stats['avg_deficit']:+.0f}" if stats["avg_deficit"] != 0 else "0"
            text = (
                f"📊 <b>Статус недели:</b> {status_label}\n\n"
                f"Средний дефицит/профицит: {deficit_str} ккал\n"
                f"Белок выполнен: {stats['protein_days_met']} из 7 дней\n"
                f"Соблюдение плана: {stats['calorie_adherence_pct']:.0f}%\n\n"
                f"📈 Индекс недели: <b>{index_pct}%</b> — {index_label}\n\n"
            )
            if rec:
                text += f"💡 <b>Рекомендация:</b>\n{rec}"
            await bot.send_message(user_id, text, parse_mode="HTML")
            await log_notification_sent(user_id, today, "week_status")
            logger.info("Week status sent to user_id=%s status=%s", user_id, status_key)
        except Exception as e:
            logger.exception("Week status for user_id=%s: %s", user_id, e)

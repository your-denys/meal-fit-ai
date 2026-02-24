import io
from datetime import date, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from database import get_daily_totals, get_meals_range, get_weight_history, get_user, get_first_meal_date
from keyboards import stats_keyboard
from calculator import format_daily_summary

router = Router()

def make_nutrition_chart(rows, title="Калории по дням"):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        dates = [r[0][5:] for r in rows]  # MM-DD
        calories = [r[1] or 0 for r in rows]
        proteins = [r[2] or 0 for r in rows]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), facecolor="#1a1a2e")
        for ax in [ax1, ax2]:
            ax.set_facecolor("#16213e")
            ax.tick_params(colors="white")
            ax.spines[:].set_color("#444")

        ax1.bar(dates, calories, color="#e94560", alpha=0.85)
        ax1.set_title("🔥 Калории", color="white", fontsize=13)
        ax1.set_ylabel("ккал", color="white")

        ax2.bar(dates, proteins, color="#0f3460", alpha=0.85)
        ax2.set_title("🥩 Белки", color="white", fontsize=13)
        ax2.set_ylabel("г", color="white")

        plt.xticks(rotation=45, ha="right")
        plt.tight_layout(pad=2)

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        buf.seek(0)
        plt.close()
        return buf.read()
    except Exception as e:
        print(f"Chart error: {e}")
        return None

def _format_date_short(d: str) -> str:
    """'2025-02-20' -> '20.02'"""
    if len(d) >= 10:
        return f"{d[8:10]}.{d[5:7]}"
    return d


def _compute_streaks(rows: list, cal_goal: int, prot_goal: float, fat_goal: float, today_str: str) -> dict:
    """
    rows: список (date_str, cal, prot, fat, carb) по дням с данными, отсортирован по дате по возрастанию.
    Возвращает текущие серии, рекорды и общую статистику.
    """
    if not rows:
        return {
            "current_protein": 0, "current_fat": 0, "current_cal": 0,
            "best_protein": 0, "best_fat": 0, "best_cal": 0,
            "total_days": 0, "days_protein_met": 0, "days_fat_ok": 0, "days_cal_ok": 0,
        }
    # Допуск: жиры не перебор до 110%, калории в коридоре 90–110%
    def protein_ok(prot):
        return (prot_goal or 0) > 0 and prot >= (prot_goal or 0)
    def fat_ok(fat):
        return (fat_goal or 0) <= 0 or fat <= (fat_goal or 0) * 1.10
    def cal_ok(cal):
        return (cal_goal or 0) > 0 and 0.90 * (cal_goal or 0) <= cal <= 1.10 * (cal_goal or 0)

    ok_protein = [protein_ok(r[2]) for r in rows]
    ok_fat = [fat_ok(r[3]) for r in rows]
    ok_cal = [cal_ok(r[1]) for r in rows]
    dates = [r[0] for r in rows]

    def current_streak(ok_list):
        if not dates or dates[-1] != today_str:
            return 0
        c = 0
        for i in range(len(ok_list) - 1, -1, -1):
            if not ok_list[i]:
                break
            c += 1
        return c

    def best_streak(ok_list):
        best = 0
        cur = 0
        for v in ok_list:
            if v:
                cur += 1
                best = max(best, cur)
            else:
                cur = 0
        return best

    return {
        "current_protein": current_streak(ok_protein),
        "current_fat": current_streak(ok_fat),
        "current_cal": current_streak(ok_cal),
        "best_protein": best_streak(ok_protein),
        "best_fat": best_streak(ok_fat),
        "best_cal": best_streak(ok_cal),
        "total_days": len(rows),
        "days_protein_met": sum(ok_protein),
        "days_fat_ok": sum(ok_fat),
        "days_cal_ok": sum(ok_cal),
    }


@router.message(F.text == "🏆 Результаты")
async def results_screen(message: Message):
    """Экран «Результаты»: текущие серии → рекорды → общая статистика."""
    user_id = message.from_user.id
    user = await get_user(user_id)
    first_date = await get_first_meal_date(user_id)
    today = date.today()
    today_str = today.isoformat()

    if not first_date:
        await message.answer(
            "🏆 <b>Результаты</b>\n\n"
            "Пока нет данных. Добавляй приёмы пищи — здесь появятся серии и рекорды.",
            parse_mode="HTML"
        )
        return

    from_date = first_date
    to_date = today
    rows = await get_meals_range(user_id, from_date, to_date)
    if not rows:
        await message.answer(
            "🏆 <b>Результаты</b>\n\n"
            "Пока нет данных. Добавляй приёмы пищи — здесь появятся серии и рекорды.",
            parse_mode="HTML"
        )
        return

    cal_goal = (user.get("calories_goal") or 0) if user else 0
    prot_goal = float(user.get("protein_goal") or 0) if user else 0
    fat_goal = float(user.get("fat_goal") or 0) if user else 0
    data = _compute_streaks(rows, cal_goal, prot_goal, fat_goal, today_str)

    # 1) Текущая серия (если есть цели)
    lines = ["🏆 <b>Результаты</b>\n", "🔥 <b>Текущая серия</b>"]
    if cal_goal or prot_goal or fat_goal:
        if data["current_protein"] > 0:
            lines.append(f"🟢 Закрыл норму белка — <b>{data['current_protein']} дн.</b> подряд")
        else:
            lines.append("🥩 Белок — пока нет серии")
        if fat_goal > 0:
            if data["current_fat"] > 0:
                lines.append(f"🟢 Не перебор жиров — <b>{data['current_fat']} дн.</b> подряд")
            else:
                lines.append("🧈 Жиры — пока нет серии")
        if cal_goal > 0:
            if data["current_cal"] > 0:
                lines.append(f"🟢 Попадание в калории — <b>{data['current_cal']} дн.</b> подряд")
            else:
                lines.append("🔥 Калории — пока нет серии")
    else:
        lines.append("Заполни цели в профиле — появятся серии по белку, жирам и калориям.")

    # 2) Рекорды
    lines.append("\n🏆 <b>Рекорды</b>")
    lines.append(f"🥩 Лучшая серия по белку — <b>{data['best_protein']} дн.</b>")
    lines.append(f"🧈 Лучший результат по жирам — <b>{data['best_fat']} дн.</b>")
    lines.append(f"🔥 Рекорд соблюдения калорий — <b>{data['best_cal']} дн.</b>")

    # 3) Общая статистика
    lines.append("\n📊 <b>Всего</b>")
    lines.append(f"Дней в системе: <b>{data['total_days']}</b>")
    lines.append(f"Белок закрыт: <b>{data['days_protein_met']}</b> дн.")
    lines.append(f"Жиры в норме: <b>{data['days_fat_ok']}</b> дн.")
    lines.append(f"Калории в норме: <b>{data['days_cal_ok']}</b> дн.")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data == "stats_open")
async def stats_open_from_profile(callback: CallbackQuery):
    """Открыть блок «Статистика» из профиля (кнопка «📊 Статистика»)."""
    user_id = callback.from_user.id
    user = await get_user(user_id)
    totals = await get_daily_totals(user_id)
    if user:
        text = format_daily_summary(totals, user)
    else:
        text = (
            f"📊 <b>Сегодня:</b>\n\n"
            f"🔥 {totals['calories']} ккал\n"
            f"🥩 Белки: {totals['protein']:.1f} г\n"
            f"🧈 Жиры: {totals['fat']:.1f} г\n"
            f"🍞 Углеводы: {totals['carbs']:.1f} г"
        )
    await callback.message.answer(
        f"📊 <b>Статистика</b>\n\n{text}\n\nВыбери период:",
        parse_mode="HTML",
        reply_markup=stats_keyboard()
    )
    await callback.answer()


@router.message(F.text == "📊 Статистика")
async def stats_menu(message: Message):
    """По умолчанию показываем за сегодня, ниже кнопки Неделя / Месяц."""
    user_id = message.from_user.id
    user = await get_user(user_id)
    totals = await get_daily_totals(user_id)
    if user:
        text = format_daily_summary(totals, user)
    else:
        text = (
            f"📊 <b>Сегодня:</b>\n\n"
            f"🔥 {totals['calories']} ккал\n"
            f"🥩 Белки: {totals['protein']:.1f} г\n"
            f"🧈 Жиры: {totals['fat']:.1f} г\n"
            f"🍞 Углеводы: {totals['carbs']:.1f} г"
        )
    await message.answer(
        f"📊 <b>Статистика</b>\n\n{text}\n\nВыбери период:",
        parse_mode="HTML",
        reply_markup=stats_keyboard()
    )


@router.callback_query(F.data == "stats_week")
async def stats_week(callback: CallbackQuery):
    user_id = callback.from_user.id
    today = date.today()
    from_date = today - timedelta(days=6)
    rows = await get_meals_range(user_id, from_date, today)

    if not rows:
        await callback.message.answer("Нет данных за последние 7 дней.")
        await callback.answer()
        return

    lines = []
    for r in rows:
        d, cal, prot, fat, carbs = r[0], r[1] or 0, r[2] or 0, r[3] or 0, r[4] or 0
        lines.append(f"• {_format_date_short(d)} — 🔥 {int(cal)} ккал, 🥩 {prot:.0f} г, 🧈 {fat:.0f} г, 🍞 {carbs:.0f} г")
    text = "📆 <b>За неделю (по дням)</b>\n\n" + "\n".join(lines)
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "stats_month")
async def stats_month(callback: CallbackQuery):
    user_id = callback.from_user.id
    today = date.today()
    from_date = today - timedelta(days=29)
    rows = await get_meals_range(user_id, from_date, today)

    if not rows:
        await callback.message.answer("Нет данных за последние 30 дней.")
        await callback.answer()
        return

    lines = []
    for r in rows:
        d, cal, prot, fat, carbs = r[0], r[1] or 0, r[2] or 0, r[3] or 0, r[4] or 0
        lines.append(f"• {_format_date_short(d)} — 🔥 {int(cal)} ккал, 🥩 {prot:.0f} г, 🧈 {fat:.0f} г, 🍞 {carbs:.0f} г")
    total_days = len(rows)
    avg_cal = sum(r[1] or 0 for r in rows) / total_days
    text = "🗓 <b>За месяц (по дням)</b>\n\n" + "\n".join(lines) + f"\n\nДней с едой: {total_days} · в среднем 🔥 {avg_cal:.0f} ккал/день"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "stats_weight")
async def stats_weight(callback: CallbackQuery):
    """Список записей веса (последние 30)."""
    user_id = callback.from_user.id
    rows = await get_weight_history(user_id, 30)

    if not rows:
        await callback.message.answer("Пока нет записей веса. Используй «⚖️ Записать вес».")
        await callback.answer()
        return

    user = await get_user(user_id)
    lines = ["⚖️ <b>Список веса</b>\n"]
    for w, d in rows:
        date_short = d[8:10] + "." + d[5:7] + "." + d[0:4] if len(d) >= 10 else d
        lines.append(f"• {date_short} — <b>{w} кг</b>")
    if user and user.get("target_weight"):
        diff = user["weight"] - user["target_weight"]
        lines.append(f"\n📍 До цели: {abs(diff):.1f} кг")
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()

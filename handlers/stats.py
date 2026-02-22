import io
from datetime import date, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from database import get_daily_totals, get_meals_range, get_weight_history, get_user
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

def make_weight_chart(rows):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        rows = list(reversed(rows))
        dates = [r[1][5:] for r in rows]
        weights = [r[0] for r in rows]

        fig, ax = plt.subplots(figsize=(10, 4), facecolor="#1a1a2e")
        ax.set_facecolor("#16213e")
        ax.tick_params(colors="white")
        ax.spines[:].set_color("#444")

        ax.plot(dates, weights, color="#e94560", marker="o", linewidth=2, markersize=5)
        ax.fill_between(range(len(dates)), weights, alpha=0.15, color="#e94560")
        ax.set_title("⚖️ Динамика веса", color="white", fontsize=13)
        ax.set_ylabel("кг", color="white")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        buf.seek(0)
        plt.close()
        return buf.read()
    except Exception as e:
        print(f"Weight chart error: {e}")
        return None

def _format_date_short(d: str) -> str:
    """'2025-02-20' -> '20.02'"""
    if len(d) >= 10:
        return f"{d[8:10]}.{d[5:7]}"
    return d


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
    user_id = callback.from_user.id
    rows = await get_weight_history(user_id, 30)

    if not rows or len(rows) < 2:
        await callback.message.answer("Нужно хотя бы 2 записи веса для графика. Записывай вес регулярно!")
        await callback.answer()
        return

    chart = make_weight_chart(rows)
    user = await get_user(user_id)
    caption = "⚖️ <b>Динамика веса</b>"
    if user and user.get("target_weight"):
        diff = user["weight"] - user["target_weight"]
        caption += f"\nОсталось до цели: {abs(diff):.1f} кг"

    if chart:
        await callback.message.answer_photo(
            BufferedInputFile(chart, filename="weight.png"),
            caption=caption,
            parse_mode="HTML"
        )
    await callback.answer()

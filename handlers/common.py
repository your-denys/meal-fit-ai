import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from database import get_user, get_meals_today, delete_last_meal, get_daily_totals
from keyboards import main_keyboard, stats_keyboard, meal_choice_keyboard
from calculator import format_daily_summary
from gemini_helper import get_meal_suggestion
from handlers.profile import ProfileState

router = Router()
logger = logging.getLogger(__name__)

@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    logger.info("Обработка /start от user_id=%s", message.from_user.id)
    try:
        user = get_user(message.from_user.id)
        if not user:
            await state.set_state(ProfileState.weight)
            await message.answer(
                "👋 Привет! Я <b>FitMeal AI</b> — твой трекер питания.\n\n"
                "Сначала заполним профиль — без этого не смогу считать твои цели по КБЖУ. Займёт минуту.\n\n"
                "⚖️ <b>Шаг 1/9</b> — Введи свой текущий вес (кг):",
                parse_mode="HTML",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        else:
            totals = get_daily_totals(message.from_user.id)
            summary = format_daily_summary(totals, user)
            await message.answer(
                f"👋 С возвращением!\n\n{summary}",
                parse_mode="HTML",
                reply_markup=main_keyboard()
            )
    except Exception as e:
        logger.exception("Ошибка в /start: %s", e)
        await message.answer(
            "Что-то пошло не так. Попробуй ещё раз или напиши /help.",
            reply_markup=main_keyboard()
        )

@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "📖 <b>Как пользоваться:</b>\n\n"
        "• Отправь фото еды — я посчитаю КБЖУ\n"
        "• Напиши текстом: <i>куриная грудка 150г</i>\n"
        "• <b>⚡ Быстрое добавление</b> — частые продукты одной кнопкой\n"
        "• <b>📊 Статистика</b> — графики за неделю и месяц\n"
        "• <b>⚖️ Записать вес</b> — отслеживай динамику\n"
        "• <b>👤 Профиль</b> — изменить данные и цели\n\n"
        "Команды:\n"
        "/undo — удалить последний приём пищи\n"
        "/settings — изменить профиль",
        parse_mode="HTML"
    )

@router.message(F.text == "🍽 Сегодня")
async def today(message: Message):
    user_id = message.from_user.id
    meals = get_meals_today(user_id)
    user = get_user(user_id)
    totals = get_daily_totals(user_id)

    if not meals:
        await message.answer("Сегодня ещё ничего не добавлено 🙂")
        return

    lines = ["🍽 <b>Приёмы пищи сегодня:</b>\n"]
    for i, (mid, name, cal, p, f, c) in enumerate(meals, 1):
        lines.append(f"{i}. {name} — {cal} ккал (Б:{p:.0f} Ж:{f:.0f} У:{c:.0f})")

    lines.append("")
    if user:
        lines.append(format_daily_summary(totals, user))
    else:
        lines.append(f"🔥 Итого: {totals['calories']} ккал | Б:{totals['protein']:.0f} Ж:{totals['fat']:.0f} У:{totals['carbs']:.0f}")

    await message.answer("\n".join(lines), parse_mode="HTML")

@router.message(F.text == "💡 Что съесть?")
async def what_to_eat_menu(message: Message):
    user = get_user(message.from_user.id)
    if not user or not user.get("calories_goal"):
        await message.answer(
            "Сначала заполни профиль (👤 Мой профиль), чтобы я знал твои цели по КБЖУ и мог дать совет.",
            reply_markup=main_keyboard()
        )
        return
    await message.answer(
        "Выбери приём пищи — подберу блюдо с учётом твоего прогресса за день и цели:",
        reply_markup=meal_choice_keyboard()
    )


@router.callback_query(F.data.startswith("meal_"))
async def meal_suggestion_callback(callback: CallbackQuery):
    meal_map = {
        "meal_breakfast": "завтрак",
        "meal_lunch": "обед",
        "meal_dinner": "ужин",
        "meal_snack": "перекус",
    }
    meal_type = meal_map.get(callback.data, "перекус")
    user_id = callback.from_user.id

    await callback.answer()
    await callback.message.edit_text("🔍 Подбираю блюдо...")

    user = get_user(user_id)
    totals = get_daily_totals(user_id)
    meals_today = get_meals_today(user_id)
    eaten_names = [m[1] for m in meals_today] if meals_today else []
    suggestion = get_meal_suggestion(totals, user, meal_type, eaten_today=eaten_names)

    if not suggestion:
        await callback.message.edit_text(
            "Не удалось сформировать совет. Проверь, что в профиле заданы цели по КБЖУ."
        )
        return
    await callback.message.edit_text(f"💡 <b>Что съесть на {meal_type}:</b>\n\n{suggestion}", parse_mode="HTML")


@router.message(Command("undo"))
async def undo(message: Message):
    deleted = delete_last_meal(message.from_user.id)
    if deleted:
        await message.answer("✅ Последний приём пищи удалён.")
    else:
        await message.answer("Нечего удалять — список пустой.")

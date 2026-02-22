import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command, BaseFilter
from aiogram.fsm.context import FSMContext
from database import get_user, get_meals_today, delete_last_meal, delete_meal_by_id, get_daily_totals
from keyboards import main_keyboard, stats_keyboard, meal_choice_keyboard
from calculator import format_daily_summary
from gemini_helper import get_meal_suggestion, answer_user_question
from handlers.profile import ProfileState
from handlers.food import FoodState


class ReplyToBotFilter(BaseFilter):
    """Сообщение — ответ на сообщение бота; при этом не в состоянии правки еды (чтобы не перехватывать «это рис»)."""
    async def __call__(self, message: Message, state: FSMContext) -> bool:
        if not message.reply_to_message or not message.reply_to_message.from_user.is_bot:
            return False
        s = await state.get_state()
        if s in (FoodState.waiting_correction.state, FoodState.waiting_confirm.state):
            return False
        return True

router = Router()
logger = logging.getLogger(__name__)

@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    logger.info("Обработка /start от user_id=%s", message.from_user.id)
    try:
        user = await get_user(message.from_user.id)
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
            totals = await get_daily_totals(message.from_user.id)
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

# Краткое описание бота (можно вставить в BotFather → Edit Bot → Description)
BOT_DESCRIPTION = (
    "Трекер питания с ИИ: считаю КБЖУ по фото и тексту, подбираю блюда под твои цели, "
    "напоминаю поесть, строю графики. Цели: похудение, набор, поддержание, рекомпозиция, сушка."
)

# Полный текст вкладки «Что я умею»
WHAT_I_CAN_DO = """📖 <b>Что я умею</b>

<b>🍽 Учёт еды</b>
• <b>📷 Добавить еду</b> — сфоткай тарелку или напиши: <i>куриная грудка 150г</i>. Я посчитаю КБЖУ и предложу подтвердить или исправить.
• <b>🍽 Сегодня</b> — список приёмов пищи за день и итоги: калории, белки, жиры, углеводы к твоим целям.
• <b>⚡ Быстрое добавление</b> — избранные продукты одной кнопкой. Можно добавлять и удалять свои «быстрые» блюда.

<b>💡 Советы</b>
• <b>💡 Что съесть?</b> — выбери приём (завтрак, обед, ужин, перекус). Подберу блюдо с учётом того, что ты уже съел, и твоих целей по КБЖУ.

<b>👤 Профиль и цели</b>
• Анкета: вес, рост, возраст, пол, активность, тренировки (сколько раз, тип, длительность), цель — похудеть, набрать массу, поддержание, рекомпозиция или сушка. ИИ рассчитает персональные КБЖУ; можно подправить вручную.
• <b>🔔 Напоминания</b> — «пора поесть» 2, 3 или 4 раза в день с учётом недобора и твоего рациона. Включить/выключить и выбрать количество в профиле.
• <b>⚖️ Записать вес</b> — ввожу вес, цели пересчитываются под новый вес.

<b>📊 Статистика</b>
• Итоги за сегодня, графики калорий и белков за неделю и месяц, график веса.

<b>💬 Общение с ИИ</b>
Можешь <b>ответить</b> на любое моё сообщение (напоминание, совет, результат по еде) — напиши вопрос или уточнение текстом, и я отвечу в контексте этого сообщения.

<b>Команды</b>
/undo — удалить последний приём пищи за сегодня
/settings — открыть профиль
/help — это сообщение"""


@router.message(Command("help"))
@router.message(F.text == "📖 Что я умею")
async def help_cmd(message: Message):
    await message.answer(WHAT_I_CAN_DO, parse_mode="HTML")


@router.message(F.text, F.reply_to_message, ReplyToBotFilter())
async def reply_to_bot_question(message: Message):
    """Ответ пользователя на сообщение бота (напоминание, совет и т.д.) — отправляем в ИИ с контекстом."""
    context = message.reply_to_message.text or message.reply_to_message.caption or ""
    reply = answer_user_question(context, message.text or "")
    if reply:
        await message.answer(reply)
    else:
        await message.answer("Не получилось ответить. Попробуй переформулировать или напиши /help.")

def _today_text(meals: list, totals: dict, user: dict | None) -> str:
    lines = ["🍽 <b>Приёмы пищи сегодня:</b>\n"]
    for i, (mid, name, cal, p, f, c) in enumerate(meals, 1):
        lines.append(f"{i}. {name} — {cal} ккал (Б:{p:.0f} Ж:{f:.0f} У:{c:.0f})")
    lines.append("")
    if user:
        lines.append(format_daily_summary(totals, user))
    else:
        lines.append(f"🔥 Итого: {totals['calories']} ккал | Б:{totals['protein']:.0f} Ж:{totals['fat']:.0f} У:{totals['carbs']:.0f}")
    return "\n".join(lines)


@router.message(F.text == "🍽 Сегодня")
async def today(message: Message):
    user_id = message.from_user.id
    meals = await get_meals_today(user_id)
    user = await get_user(user_id)
    totals = await get_daily_totals(user_id)

    if not meals:
        await message.answer("Сегодня ещё ничего не добавлено 🙂")
        return

    text = _today_text(meals, totals, user)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить блюдо", callback_data="today_delete_menu")],
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "today_delete_menu")
async def today_delete_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    meals = await get_meals_today(user_id)
    await callback.answer()
    if not meals:
        await callback.message.edit_text("Сегодня ещё ничего не добавлено 🙂")
        return
    buttons = [
        [InlineKeyboardButton(text=f"🗑 {name} — {cal} ккал", callback_data=f"today_del_{mid}")]
        for mid, name, cal, p, f, c in meals
    ]
    await callback.message.edit_text(
        "Выбери блюдо для удаления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("today_del_"))
async def today_del_meal(callback: CallbackQuery):
    try:
        meal_id = int(callback.data.replace("today_del_", ""))
    except ValueError:
        await callback.answer("Ошибка")
        return
    user_id = callback.from_user.id
    deleted = await delete_meal_by_id(meal_id, user_id)
    await callback.answer("Удалено" if deleted else "Не найдено")
    if not deleted:
        return
    meals = await get_meals_today(user_id)
    user = await get_user(user_id)
    totals = await get_daily_totals(user_id)
    if not meals:
        await callback.message.edit_text("✅ Блюдо удалено. Сегодня больше нет записей.")
        return
    text = _today_text(meals, totals, user)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить блюдо", callback_data="today_delete_menu")],
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@router.message(F.text == "💡 Что съесть?")
async def what_to_eat_menu(message: Message):
    user = await get_user(message.from_user.id)
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

    user = await get_user(user_id)
    totals = await get_daily_totals(user_id)
    meals_today = await get_meals_today(user_id)
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
    deleted = await delete_last_meal(message.from_user.id)
    if deleted:
        await message.answer("✅ Последний приём пищи удалён.")
    else:
        await message.answer("Нечего удалять — список пустой.")

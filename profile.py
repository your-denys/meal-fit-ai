from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from database import get_user, save_user, log_weight
from keyboards import main_keyboard, activity_keyboard, goal_keyboard, gender_keyboard
from gemini_helper import calculate_goals_ai
from calculator import calculate_goals

router = Router()

class ProfileState(StatesGroup):
    name = State()
    weight = State()
    height = State()
    age = State()
    gender = State()
    activity = State()
    goal = State()
    goal_custom = State()
    target_weight = State()

class WeightState(StatesGroup):
    entering = State()

GOAL_LABELS = {
    "loss": "📉 Похудеть",
    "gain": "📈 Набрать массу",
    "maintain": "⚖️ Поддерживать",
    "cutting": "🔥 Сушка",
}

ACTIVITY_LABELS = {
    "sedentary": "🪑 Сидячий",
    "light": "🚶 Немного активный",
    "moderate": "🏃 Активный",
    "high": "💪 Очень активный",
}

@router.message(F.text == "👤 Мой профиль")
@router.message(Command("settings"))
async def profile_button(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user:
        await state.set_state(ProfileState.name)
        await message.answer("👋 Профиль не заполнен. Давай настроим!\n\nКак тебя зовут?")
    else:
        goal_label = GOAL_LABELS.get(user.get("goal", ""), user.get("goal", "—"))
        activity_label = ACTIVITY_LABELS.get(user.get("activity", ""), "—")
        await message.answer(
            f"👤 <b>Твой профиль:</b>\n\n"
            f"📛 Имя: {user.get('name', '—')}\n"
            f"⚖️ Вес: {user.get('weight', '—')} кг\n"
            f"📏 Рост: {user.get('height', '—')} см\n"
            f"🎂 Возраст: {user.get('age', '—')} лет\n"
            f"🎯 Цель: {goal_label}\n"
            f"🏃 Активность: {activity_label}\n"
            f"🏁 Желаемый вес: {user.get('target_weight', '—')} кг\n\n"
            f"<b>Ежедневные цели:</b>\n"
            f"🔥 {user.get('calories_goal', '?')} ккал\n"
            f"🥩 Белки: {user.get('protein_goal', '?')} г\n"
            f"🧈 Жиры: {user.get('fat_goal', '?')} г\n"
            f"🍞 Углеводы: {user.get('carbs_goal', '?')} г\n\n"
            f"Чтобы обновить данные — /setup",
            parse_mode="HTML"
        )

@router.message(Command("setup"))
async def start_onboarding(message: Message, state: FSMContext):
    await state.set_state(ProfileState.name)
    await message.answer("👋 Давай настроим профиль!\n\nКак тебя зовут?")

@router.message(ProfileState.name)
async def get_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(ProfileState.weight)
    await message.answer(f"Приятно познакомиться, {message.text}! 💪\n\nВведи свой текущий вес (кг):")

@router.message(ProfileState.weight)
async def get_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.replace(",", "."))
        await state.update_data(weight=weight)
        await state.set_state(ProfileState.height)
        await message.answer("Введи свой рост (см):")
    except ValueError:
        await message.answer("Введи число, например: 75")

@router.message(ProfileState.height)
async def get_height(message: Message, state: FSMContext):
    try:
        height = float(message.text.replace(",", "."))
        await state.update_data(height=height)
        await state.set_state(ProfileState.age)
        await message.answer("Введи свой возраст:")
    except ValueError:
        await message.answer("Введи число, например: 175")

@router.message(ProfileState.age)
async def get_age(message: Message, state: FSMContext):
    try:
        age = int(message.text)
        await state.update_data(age=age)
        await state.set_state(ProfileState.gender)
        await message.answer("Выбери пол:", reply_markup=gender_keyboard())
    except ValueError:
        await message.answer("Введи число, например: 25")

@router.callback_query(F.data.startswith("gender_"), ProfileState.gender)
async def get_gender(callback: CallbackQuery, state: FSMContext):
    gender = callback.data.replace("gender_", "")
    await state.update_data(gender=gender)
    await state.set_state(ProfileState.activity)
    await callback.message.edit_text("Выбери уровень активности:", reply_markup=activity_keyboard())
    await callback.answer()

@router.callback_query(F.data.startswith("activity_"), ProfileState.activity)
async def get_activity(callback: CallbackQuery, state: FSMContext):
    activity = callback.data.replace("activity_", "")
    await state.update_data(activity=activity)
    await state.set_state(ProfileState.goal)
    await callback.message.edit_text("Какая твоя цель?", reply_markup=goal_keyboard())
    await callback.answer()

@router.callback_query(F.data.startswith("goal_"), ProfileState.goal)
async def get_goal(callback: CallbackQuery, state: FSMContext):
    goal = callback.data.replace("goal_", "")
    if goal == "custom":
        await state.set_state(ProfileState.goal_custom)
        await callback.message.edit_text(
            "✏️ Опиши свою цель своими словами, например:\n"
            "<i>Хочу подсушиться и при этом не терять силу, занимаюсь 4 раза в неделю</i>",
            parse_mode="HTML"
        )
    else:
        await state.update_data(goal=goal)
        await state.set_state(ProfileState.target_weight)
        await callback.message.edit_text("Введи желаемый вес (кг).\nЕсли не важно — отправь 0:")
    await callback.answer()

@router.message(ProfileState.goal_custom)
async def get_goal_custom(message: Message, state: FSMContext):
    await state.update_data(goal=message.text)
    await state.set_state(ProfileState.target_weight)
    await message.answer("Введи желаемый вес (кг).\nЕсли не важно — отправь 0:")

@router.message(ProfileState.target_weight)
async def get_target_weight(message: Message, state: FSMContext):
    try:
        target = float(message.text.replace(",", "."))
        data = await state.get_data()
        target_weight = target if target > 0 else None

        await message.answer("🤖 ИИ рассчитывает твои цели, подожди секунду...")

        result = calculate_goals_ai(
            data["weight"], data["height"], data["age"],
            data["gender"], data["activity"], data["goal"],
            target_weight
        )

        if result:
            cal = result["calories"]
            prot = result["protein"]
            fat = result["fat"]
            carbs = result["carbs"]
            comment = result.get("comment", "")
        else:
            goal_key = data["goal"] if data["goal"] in ["loss", "gain", "maintain", "cutting"] else "maintain"
            cal, prot, fat, carbs = calculate_goals(
                data["weight"], data["height"], data["age"],
                data["gender"], data["activity"], goal_key
            )
            comment = ""

        goal_label = GOAL_LABELS.get(data["goal"], data["goal"])

        user_data = {
            "name": data["name"],
            "weight": data["weight"],
            "height": data["height"],
            "age": data["age"],
            "gender": data["gender"],
            "activity": data["activity"],
            "goal": data["goal"],
            "target_weight": target_weight,
            "calories_goal": cal,
            "protein_goal": prot,
            "fat_goal": fat,
            "carbs_goal": carbs,
        }
        save_user(message.from_user.id, user_data)
        await state.clear()

        await message.answer(
            f"✅ <b>Профиль сохранён!</b>\n\n"
            f"🎯 Цель: {goal_label}\n"
            f"🏁 Желаемый вес: {target_weight or '—'} кг\n\n"
            f"<b>Твои ежедневные цели:</b>\n"
            f"🔥 Калории: <b>{cal} ккал</b>\n"
            f"🥩 Белки: <b>{prot} г</b>\n"
            f"🧈 Жиры: <b>{fat} г</b>\n"
            f"🍞 Углеводы: <b>{carbs} г</b>\n\n"
            + (f"💬 <i>{comment}</i>\n\n" if comment else "")
            + f"Теперь можно добавлять еду! 📷",
            parse_mode="HTML",
            reply_markup=main_keyboard()
        )
    except ValueError:
        await message.answer("Введи число, например: 75 или 0")

# --- Weight logging ---

@router.message(F.text == "⚖️ Записать вес")
async def weight_prompt(message: Message, state: FSMContext):
    await state.set_state(WeightState.entering)
    await message.answer("Введи свой текущий вес (кг):")

@router.message(WeightState.entering)
async def save_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.replace(",", "."))
        log_weight(message.from_user.id, weight)
        await state.clear()

        user = get_user(message.from_user.id)
        text = f"✅ Вес <b>{weight} кг</b> записан!"
        if user and user.get("target_weight"):
            diff = abs(weight - user["target_weight"])
            arrow = "осталось до цели" if weight > user["target_weight"] else "ниже цели на"
            text += f"\n📍 {arrow}: <b>{diff:.1f} кг</b>"

        await message.answer(text, parse_mode="HTML")
    except ValueError:
        await message.answer("Введи число, например: 74.5")

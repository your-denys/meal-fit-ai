from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
from database import get_user, save_user, log_weight
from keyboards import main_keyboard, gender_keyboard
from gemini_helper import calculate_goals_ai
from calculator import calculate_goals, calculate_water_goal

router = Router()

class ProfileState(StatesGroup):
    weight = State()
    height = State()
    age = State()
    gender = State()
    lifestyle = State()
    training_count = State()
    training_type = State()
    training_duration = State()
    goal = State()
    goal_custom = State()
    goal_pace = State()
    target_weight = State()

class WeightState(StatesGroup):
    entering = State()


class EditKBJUState(StatesGroup):
    entering = State()

GOAL_LABELS = {
    "loss": "📉 Похудеть",
    "gain": "📈 Набрать массу",
    "maintain": "⚖️ Поддерживать",
    "cutting": "🔥 Сушка",
    "recomp": "🔄 Рекомпозиция",
}

ACTIVITY_LABELS = {
    "sedentary": "🪑 Сидячий",
    "light": "🚶 Среднеактивный",
    "active": "💪 Физически активный",
}

def lifestyle_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪑 Сидячий (офис, минимум движения)", callback_data="lifestyle_sedentary")],
        [InlineKeyboardButton(text="🚶 Среднеактивный (хожу пешком, стою)", callback_data="lifestyle_light")],
        [InlineKeyboardButton(text="💪 Физически активный (физический труд)", callback_data="lifestyle_active")],
    ])

def training_count_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Не тренируюсь", callback_data="tc_0")],
        [
            InlineKeyboardButton(text="1-2 раза", callback_data="tc_1"),
            InlineKeyboardButton(text="3-4 раза", callback_data="tc_3"),
        ],
        [
            InlineKeyboardButton(text="5-6 раз", callback_data="tc_5"),
            InlineKeyboardButton(text="Каждый день", callback_data="tc_7"),
        ],
    ])

def training_type_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏋️ Силовые", callback_data="tt_strength")],
        [InlineKeyboardButton(text="🏃 Кардио", callback_data="tt_cardio")],
        [InlineKeyboardButton(text="🔀 Смешанные", callback_data="tt_mixed")],
    ])

def training_duration_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="30 мин", callback_data="td_30"),
            InlineKeyboardButton(text="45 мин", callback_data="td_45"),
        ],
        [
            InlineKeyboardButton(text="60 мин", callback_data="td_60"),
            InlineKeyboardButton(text="90+ мин", callback_data="td_90"),
        ],
    ])

def goal_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📉 Похудеть", callback_data="goal_loss")],
        [InlineKeyboardButton(text="📈 Набрать массу", callback_data="goal_gain")],
        [InlineKeyboardButton(text="⚖️ Поддерживать", callback_data="goal_maintain")],
        [InlineKeyboardButton(text="🔄 Рекомпозиция", callback_data="goal_recomp")],
        [InlineKeyboardButton(text="🔥 Сушка", callback_data="goal_cutting")],
        [InlineKeyboardButton(text="✏️ Написать своё", callback_data="goal_custom")],
    ])

def goal_pace_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🐢 Медленно (комфортно, без стресса)", callback_data="pace_slow")],
        [InlineKeyboardButton(text="⚡ Быстро (агрессивно, строгий режим)", callback_data="pace_fast")],
    ])

# --- Handlers ---

@router.message(F.text == "👤 Мой профиль")
@router.message(Command("settings"))
async def profile_button(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if not user:
        await state.set_state(ProfileState.weight)
        await message.answer(
            "👋 Привет! Давай настроим профиль — это займёт минуту.\n\n"
            "⚖️ <b>Шаг 1/9</b> — Введи свой текущий вес (кг):",
            parse_mode="HTML"
        )
    else:
        # обновляем username при открытии профиля (актуальный @nick)
        if message.from_user.username is not None and user.get("username") != message.from_user.username:
            updates = {k: user[k] for k in user if k != "user_id"}
            updates["username"] = message.from_user.username
            await save_user(message.from_user.id, updates)
            user["username"] = message.from_user.username
        goal_label = GOAL_LABELS.get(user.get("goal", ""), user.get("goal", "—"))
        activity_label = ACTIVITY_LABELS.get(user.get("activity", ""), "—")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить цели КБЖУ", callback_data="profile_edit_kbju")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="stats_open")],
            [InlineKeyboardButton(text="🎛 Центр управления", callback_data="profile_control_center")],
        ])
        await message.answer(
            f"👤 <b>Твой профиль:</b>\n\n"
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
            f"🍞 Углеводы: {user.get('carbs_goal', '?')} г\n"
            f"💧 Вода: {user.get('water_goal') or '—'} мл\n\n"
            f"Чтобы обновить данные профиля — /setup",
            parse_mode="HTML",
            reply_markup=kb
        )


def _profile_text_and_kb(user: dict):
    """Текст и клавиатура блока «Мой профиль» для повторного показа (например, из «Назад»)."""
    goal_label = GOAL_LABELS.get(user.get("goal", ""), user.get("goal", "—"))
    activity_label = ACTIVITY_LABELS.get(user.get("activity", ""), "—")
    text = (
        f"👤 <b>Твой профиль:</b>\n\n"
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
        f"🍞 Углеводы: {user.get('carbs_goal', '?')} г\n"
        f"💧 Вода: {user.get('water_goal') or '—'} мл\n\n"
        f"Чтобы обновить данные профиля — /setup"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить цели КБЖУ", callback_data="profile_edit_kbju")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats_open")],
        [InlineKeyboardButton(text="🎛 Центр управления", callback_data="profile_control_center")],
    ])
    return text, kb


def control_center_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Напоминания «пора поесть»", callback_data="profile_reminders")],
        [InlineKeyboardButton(text="👋 Напоминания о трекинге", callback_data="profile_reengage")],
        [InlineKeyboardButton(text="🎯 О прогрессе", callback_data="profile_progress")],
        [InlineKeyboardButton(text="📊 Статус недели", callback_data="profile_week_status")],
        [InlineKeyboardButton(text="◀️ Назад в профиль", callback_data="profile_back_to_profile")],
    ])


@router.callback_query(F.data == "profile_control_center")
async def profile_control_center_screen(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала заполни профиль.")
        return
    await callback.answer()
    await callback.message.edit_text(
        "🎛 <b>Центр управления</b>\n\n"
        "Здесь можно включить или выключить разные уведомления:",
        parse_mode="HTML",
        reply_markup=control_center_keyboard()
    )


@router.callback_query(F.data == "profile_back_to_profile")
async def profile_back_to_profile(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer()
        return
    text, kb = _profile_text_and_kb(user)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


# --- Напоминания «пора поесть» ---
KBJU_FIELDS = {
    "cal": ("calories_goal", "🔥 Калории (ккал)", 500, 5000),
    "prot": ("protein_goal", "🥩 Белки (г)", 20, 300),
    "fat": ("fat_goal", "🧈 Жиры (г)", 10, 200),
    "carb": ("carbs_goal", "🍞 Углеводы (г)", 50, 600),
}


def kbju_edit_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔥 Калории", callback_data="profile_kbju_cal"),
            InlineKeyboardButton(text="🥩 Белки", callback_data="profile_kbju_prot"),
        ],
        [
            InlineKeyboardButton(text="🧈 Жиры", callback_data="profile_kbju_fat"),
            InlineKeyboardButton(text="🍞 Углеводы", callback_data="profile_kbju_carb"),
        ],
    ])


@router.callback_query(F.data == "profile_edit_kbju")
async def profile_edit_kbju_start(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала заполни профиль.")
        return
    await callback.answer()
    cal = user.get("calories_goal") or 0
    prot = user.get("protein_goal") or 0
    fat = user.get("fat_goal") or 0
    carb = user.get("carbs_goal") or 0
    await callback.message.answer(
        f"✏️ <b>Ручная корректировка целей КБЖУ</b>\n\n"
        f"Сейчас: 🔥 {cal} ккал · 🥩 {prot} г · 🧈 {fat} г · 🍞 {carb} г\n\n"
        f"Выбери, что изменить — затем введи одно число:",
        parse_mode="HTML",
        reply_markup=kbju_edit_keyboard()
    )


@router.callback_query(F.data.startswith("profile_kbju_"))
async def profile_kbju_choose_field(callback: CallbackQuery, state: FSMContext):
    key = callback.data.replace("profile_kbju_", "")
    if key not in KBJU_FIELDS:
        await callback.answer()
        return
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала заполни профиль.")
        return
    await callback.answer()
    field_key, label, lo, hi = KBJU_FIELDS[key]
    current = user.get(field_key) or 0
    await state.set_state(EditKBJUState.entering)
    await state.update_data(kbju_field=field_key, kbju_lo=lo, kbju_hi=hi)
    await callback.message.answer(
        f"✏️ {label}\nСейчас: <b>{current}</b>. Введи новое значение (от {lo} до {hi}):",
        parse_mode="HTML"
    )


@router.message(EditKBJUState.entering, F.text)
async def profile_edit_kbju_apply(message: Message, state: FSMContext):
    data = await state.get_data()
    field_key = data.get("kbju_field")
    lo, hi = data.get("kbju_lo", 0), data.get("kbju_hi", 9999)
    if not field_key:
        await state.clear()
        return
    try:
        value = int(message.text.strip().replace(" ", ""))
    except ValueError:
        await message.answer(f"Введи одно целое число от {lo} до {hi}.")
        return
    if value < lo or value > hi:
        await message.answer(f"Значение должно быть от {lo} до {hi}. Введи снова.")
        return
    user = await get_user(message.from_user.id)
    if not user:
        await state.clear()
        return
    updates = {k: user[k] for k in user if k != "user_id"}
    updates[field_key] = value
    water = calculate_water_goal(
        user.get("weight") or 70,
        user.get("goal") or "maintain",
        user.get("pace") or "slow",
        updates.get("carbs_goal", user.get("carbs_goal")) or 200
    )
    updates["water_goal"] = water
    updates["username"] = message.from_user.username
    await save_user(message.from_user.id, updates)
    await state.clear()
    u = await get_user(message.from_user.id)
    await message.answer(
        f"✅ Обновлено. Цели: 🔥 {u.get('calories_goal')} ккал · 🥩 {u.get('protein_goal')} г · "
        f"🧈 {u.get('fat_goal')} г · 🍞 {u.get('carbs_goal')} г · 💧 {u.get('water_goal')} мл",
        parse_mode="HTML"
    )


# --- Напоминания «пора поесть» ---

def reminders_keyboard(user: dict):
    enabled = user.get("reminders_enabled") is not None and user.get("reminders_enabled") != 0
    per_day = user.get("reminders_per_day") or 3
    row1 = []
    if enabled:
        row1.append(InlineKeyboardButton(text="🔕 Выключить", callback_data="profile_reminders_off"))
    else:
        row1.append(InlineKeyboardButton(text="🔔 Включить", callback_data="profile_reminders_on"))
    row2 = [
        InlineKeyboardButton(text="2 в день" + (" ✓" if per_day == 2 else ""), callback_data="profile_reminders_2"),
        InlineKeyboardButton(text="3 в день" + (" ✓" if per_day == 3 else ""), callback_data="profile_reminders_3"),
        InlineKeyboardButton(text="4 в день" + (" ✓" if per_day == 4 else ""), callback_data="profile_reminders_4"),
    ]
    row3 = [InlineKeyboardButton(text="◀️ В центр управления", callback_data="profile_control_center")]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2, row3])


@router.callback_query(F.data == "profile_reminders")
async def profile_reminders_screen(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала заполни профиль.")
        return
    await callback.answer()
    enabled = user.get("reminders_enabled") is not None and user.get("reminders_enabled") != 0
    per_day = user.get("reminders_per_day") or 3
    status = "включены" if enabled else "выключены"
    text = (
        f"🔔 <b>Напоминания «пора поесть»</b>\n\n"
        f"Сейчас: <b>{status}</b>. До {per_day} напоминаний в день.\n"
        f"Бот смотрит недобор по калориям/белку/углеводам и подсказывает, что съесть.\n"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reminders_keyboard(user))


@router.callback_query(F.data.startswith("profile_reminders_"))
async def profile_reminders_toggle(callback: CallbackQuery):
    action = callback.data.replace("profile_reminders_", "")
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer()
        return
    updates = {k: user[k] for k in user if k != "user_id"}
    updates["username"] = callback.from_user.username
    if action == "off":
        updates["reminders_enabled"] = 0
    elif action == "on":
        updates["reminders_enabled"] = 1
    elif action in ("2", "3", "4"):
        updates["reminders_enabled"] = 1
        updates["reminders_per_day"] = int(action)
    else:
        await callback.answer()
        return
    await save_user(callback.from_user.id, updates)
    await callback.answer("Сохранено")
    user = await get_user(callback.from_user.id)
    status = "включены" if (user.get("reminders_enabled") or 0) != 0 else "выключены"
    per_day = user.get("reminders_per_day") or 3
    text = (
        f"🔔 <b>Напоминания «пора поесть»</b>\n\n"
        f"Сейчас: <b>{status}</b>. До {per_day} напоминаний в день.\n\n"
        f"Включи/выключи и выбери количество в день:"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reminders_keyboard(user))


def reengage_keyboard(user: dict):
    enabled = user.get("reengage_enabled") is None or user.get("reengage_enabled") != 0
    row1 = [InlineKeyboardButton(text="🔕 Выключить", callback_data="profile_reengage_off")] if enabled else [InlineKeyboardButton(text="🔔 Включить", callback_data="profile_reengage_on")]
    row2 = [InlineKeyboardButton(text="◀️ В центр управления", callback_data="profile_control_center")]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])


@router.callback_query(F.data == "profile_reengage")
async def profile_reengage_screen(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала заполни профиль.")
        return
    await callback.answer()
    enabled = user.get("reengage_enabled") is None or user.get("reengage_enabled") != 0
    status = "включены" if enabled else "выключены"
    text = (
        "👋 <b>Напоминания о трекинге</b>\n\n"
        "Если ты долго не открываешь бота, мы пришлём мягкое напоминание:\n"
        "• через 2 дня — «Я тебя потерял 👀 Продолжаем следить за прогрессом?»\n"
        "• через 4–5 дней — короткий мотивирующий текст.\n\n"
        f"Сейчас: <b>{status}</b>."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reengage_keyboard(user))


@router.callback_query(F.data.startswith("profile_reengage_"))
async def profile_reengage_toggle(callback: CallbackQuery):
    action = callback.data.replace("profile_reengage_", "")
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer()
        return
    updates = {k: user[k] for k in user if k != "user_id"}
    updates["username"] = callback.from_user.username
    updates["reengage_enabled"] = 1 if action == "on" else 0
    await save_user(callback.from_user.id, updates)
    await callback.answer("Сохранено")
    user = await get_user(callback.from_user.id)
    enabled = user.get("reengage_enabled") is None or user.get("reengage_enabled") != 0
    status = "включены" if enabled else "выключены"
    text = (
        "👋 <b>Напоминания о трекинге</b>\n\n"
        "Если ты долго не открываешь бота, мы пришлём мягкое напоминание.\n\n"
        f"Сейчас: <b>{status}</b>."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reengage_keyboard(user))


def progress_keyboard(user: dict):
    enabled = user.get("progress_notifications_enabled") is None or user.get("progress_notifications_enabled") != 0
    row1 = [InlineKeyboardButton(text="🔕 Выключить", callback_data="profile_progress_off")] if enabled else [InlineKeyboardButton(text="🔔 Включить", callback_data="profile_progress_on")]
    row2 = [InlineKeyboardButton(text="◀️ В центр управления", callback_data="profile_control_center")]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])


@router.callback_query(F.data == "profile_progress")
async def profile_progress_screen(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала заполни профиль.")
        return
    await callback.answer()
    enabled = user.get("progress_notifications_enabled") is None or user.get("progress_notifications_enabled") != 0
    status = "включены" if enabled else "выключены"
    text = (
        "🎯 <b>О прогрессе</b>\n\n"
        "Уведомления о достижении целей и поддержке:\n"
        "• когда ты выполнил норму белка или калорий за день — поздравление и мотивация;\n"
        "• если 5 дней подряд недобор белка или перебор калорий — мягкий совет.\n\n"
        f"Сейчас: <b>{status}</b>."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=progress_keyboard(user))


@router.callback_query(F.data.startswith("profile_progress_"))
async def profile_progress_toggle(callback: CallbackQuery):
    action = callback.data.replace("profile_progress_", "")
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer()
        return
    updates = {k: user[k] for k in user if k != "user_id"}
    updates["username"] = callback.from_user.username
    updates["progress_notifications_enabled"] = 1 if action == "on" else 0
    await save_user(callback.from_user.id, updates)
    await callback.answer("Сохранено")
    user = await get_user(callback.from_user.id)
    enabled = user.get("progress_notifications_enabled") is None or user.get("progress_notifications_enabled") != 0
    status = "включены" if enabled else "выключены"
    text = (
        "🎯 <b>О прогрессе</b>\n\n"
        "Уведомления о достижении целей и поддержке.\n\n"
        f"Сейчас: <b>{status}</b>."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=progress_keyboard(user))


def week_status_keyboard(user: dict):
    enabled = user.get("week_status_enabled") is None or user.get("week_status_enabled") != 0
    row1 = [InlineKeyboardButton(text="🔕 Выключить", callback_data="profile_week_status_off")] if enabled else [InlineKeyboardButton(text="🔔 Включить", callback_data="profile_week_status_on")]
    row2 = [InlineKeyboardButton(text="◀️ В центр управления", callback_data="profile_control_center")]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])


@router.callback_query(F.data == "profile_week_status")
async def profile_week_status_screen(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала заполни профиль.")
        return
    await callback.answer()
    enabled = user.get("week_status_enabled") is None or user.get("week_status_enabled") != 0
    status = "включён" if enabled else "выключен"
    text = (
        "📊 <b>Статус недели</b>\n\n"
        "Раз в 7 дней (в 19:00) приходит отчёт по неделе: баланс, перегруз или слишком высокий дефицит, "
        "индекс недели 0–100% и короткая рекомендация. Отправляется только если в неделе было не менее 3 дней с данными.\n\n"
        f"Сейчас: <b>{status}</b>."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=week_status_keyboard(user))


@router.callback_query(F.data.startswith("profile_week_status_"))
async def profile_week_status_toggle(callback: CallbackQuery):
    action = callback.data.replace("profile_week_status_", "")
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer()
        return
    updates = {k: user[k] for k in user if k != "user_id"}
    updates["username"] = callback.from_user.username
    updates["week_status_enabled"] = 1 if action == "on" else 0
    await save_user(callback.from_user.id, updates)
    await callback.answer("Сохранено")
    user = await get_user(callback.from_user.id)
    enabled = user.get("week_status_enabled") is None or user.get("week_status_enabled") != 0
    status = "включён" if enabled else "выключен"
    text = (
        "📊 <b>Статус недели</b>\n\n"
        "Раз в 7 дней приходит отчёт по неделе с рекомендацией.\n\n"
        f"Сейчас: <b>{status}</b>."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=week_status_keyboard(user))


@router.message(Command("setup"))
async def start_onboarding(message: Message, state: FSMContext):
    await state.set_state(ProfileState.weight)
    await message.answer(
        "👋 Давай обновим профиль!\n\n"
        "⚖️ <b>Шаг 1/9</b> — Введи свой текущий вес (кг):",
        parse_mode="HTML"
    )

# Шаг 1 — Вес
@router.message(ProfileState.weight)
async def get_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.replace(",", "."))
        await state.update_data(weight=weight)
        await state.set_state(ProfileState.height)
        await message.answer("📏 <b>Шаг 2/9</b> — Введи свой рост (см):", parse_mode="HTML")
    except ValueError:
        await message.answer("Введи число, например: 75")

# Шаг 2 — Рост
@router.message(ProfileState.height)
async def get_height(message: Message, state: FSMContext):
    try:
        height = float(message.text.replace(",", "."))
        await state.update_data(height=height)
        await state.set_state(ProfileState.age)
        await message.answer("🎂 <b>Шаг 3/9</b> — Введи свой возраст:", parse_mode="HTML")
    except ValueError:
        await message.answer("Введи число, например: 176")

# Шаг 3 — Возраст
@router.message(ProfileState.age)
async def get_age(message: Message, state: FSMContext):
    try:
        age = int(message.text)
        await state.update_data(age=age)
        await state.set_state(ProfileState.gender)
        await message.answer("👤 <b>Шаг 4/9</b> — Выбери пол:", parse_mode="HTML", reply_markup=gender_keyboard())
    except ValueError:
        await message.answer("Введи число, например: 25")

# Шаг 4 — Пол
@router.callback_query(F.data.startswith("gender_"), ProfileState.gender)
async def get_gender(callback: CallbackQuery, state: FSMContext):
    gender = callback.data.replace("gender_", "")
    await state.update_data(gender=gender)
    await state.set_state(ProfileState.lifestyle)
    await callback.message.edit_text(
        "🏠 <b>Шаг 5/9</b> — Каков твой образ жизни вне тренировок?",
        parse_mode="HTML",
        reply_markup=lifestyle_keyboard()
    )
    await callback.answer()

# Шаг 5 — Образ жизни
@router.callback_query(F.data.startswith("lifestyle_"), ProfileState.lifestyle)
async def get_lifestyle(callback: CallbackQuery, state: FSMContext):
    lifestyle = callback.data.replace("lifestyle_", "")
    await state.update_data(lifestyle=lifestyle)
    await state.set_state(ProfileState.training_count)
    await callback.message.edit_text(
        "🏋️ <b>Шаг 6/9</b> — Сколько тренировок в неделю?",
        parse_mode="HTML",
        reply_markup=training_count_keyboard()
    )
    await callback.answer()

# Шаг 6 — Кол-во тренировок
@router.callback_query(F.data.startswith("tc_"), ProfileState.training_count)
async def get_training_count(callback: CallbackQuery, state: FSMContext):
    count = callback.data.replace("tc_", "")
    await state.update_data(training_count=count)

    if count == "0":
        # Нет тренировок — пропускаем тип и длительность
        await state.update_data(training_type="none", training_duration="0")
        await state.set_state(ProfileState.goal)
        await callback.message.edit_text(
            "🎯 <b>Шаг 7/9</b> — Какая твоя цель?",
            parse_mode="HTML",
            reply_markup=goal_keyboard()
        )
    else:
        await state.set_state(ProfileState.training_type)
        await callback.message.edit_text(
            "💪 <b>Шаг 7/9</b> — Какой тип тренировок?",
            parse_mode="HTML",
            reply_markup=training_type_keyboard()
        )
    await callback.answer()

# Шаг 7 — Тип тренировок
@router.callback_query(F.data.startswith("tt_"), ProfileState.training_type)
async def get_training_type(callback: CallbackQuery, state: FSMContext):
    training_type = callback.data.replace("tt_", "")
    await state.update_data(training_type=training_type)
    await state.set_state(ProfileState.training_duration)
    await callback.message.edit_text(
        "⏱ <b>Шаг 8/9</b> — Средняя длительность тренировки?",
        parse_mode="HTML",
        reply_markup=training_duration_keyboard()
    )
    await callback.answer()

# Шаг 8 — Длительность тренировок
@router.callback_query(F.data.startswith("td_"), ProfileState.training_duration)
async def get_training_duration(callback: CallbackQuery, state: FSMContext):
    duration = callback.data.replace("td_", "")
    await state.update_data(training_duration=duration)
    await state.set_state(ProfileState.goal)
    await callback.message.edit_text(
        "🎯 <b>Шаг 9/9</b> — Какая твоя цель?",
        parse_mode="HTML",
        reply_markup=goal_keyboard()
    )
    await callback.answer()

# Шаг 9а — Цель
@router.callback_query(F.data.startswith("goal_"), ProfileState.goal)
async def get_goal(callback: CallbackQuery, state: FSMContext):
    goal = callback.data.replace("goal_", "")
    if goal == "custom":
        await state.set_state(ProfileState.goal_custom)
        await callback.message.edit_text(
            "✏️ Опиши свою цель своими словами:\n"
            "<i>Например: хочу подсушиться но сохранить силу</i>",
            parse_mode="HTML"
        )
    else:
        await state.update_data(goal=goal)
        await state.set_state(ProfileState.goal_pace)
        await callback.message.edit_text(
            "🚀 Желаемый темп изменений?",
            reply_markup=goal_pace_keyboard()
        )
    await callback.answer()

# Шаг 9б — Своя цель текстом
@router.message(ProfileState.goal_custom)
async def get_goal_custom(message: Message, state: FSMContext):
    await state.update_data(goal=message.text)
    await state.set_state(ProfileState.goal_pace)
    await message.answer("🚀 Желаемый темп изменений?", reply_markup=goal_pace_keyboard())

# Шаг 9в — Темп
@router.callback_query(F.data.startswith("pace_"), ProfileState.goal_pace)
async def get_goal_pace(callback: CallbackQuery, state: FSMContext):
    pace = callback.data.replace("pace_", "")
    await state.update_data(pace=pace)
    await state.set_state(ProfileState.target_weight)
    await callback.message.edit_text(
        "🏁 Введи желаемый вес (кг).\nЕсли не важно — отправь 0:"
    )
    await callback.answer()

# Финал — расчёт
@router.message(ProfileState.target_weight)
async def get_target_weight(message: Message, state: FSMContext):
    try:
        target = float(message.text.replace(",", "."))
        data = await state.get_data()
        target_weight = target if target > 0 else None

        await message.answer("🤖 ИИ анализирует твои данные и рассчитывает КБЖУ...")

        result = calculate_goals_ai(
            weight=data["weight"],
            height=data["height"],
            age=data["age"],
            gender=data["gender"],
            lifestyle=data["lifestyle"],
            training_count=data["training_count"],
            training_type=data["training_type"],
            training_duration=data["training_duration"],
            goal=data["goal"],
            pace=data.get("pace", "slow"),
            target_weight=target_weight
        )

        if result:
            cal = result["calories"]
            prot = result["protein"]
            fat = result["fat"]
            carbs = result["carbs"]
            bmr = result.get("bmr") or result.get("BMR") or "—"
            tdee = result.get("tdee") or result.get("TDEE") or "—"
            comment = result.get("comment", "")
            nuances = result.get("nuances", "")
        else:
            goal_key = data["goal"] if data["goal"] in ["loss", "gain", "maintain", "cutting", "recomp"] else "maintain"
            cal, prot, fat, carbs = calculate_goals(
                data["weight"], data["height"], data["age"],
                data["gender"], data["lifestyle"], goal_key
            )
            bmr = tdee = "—"
            comment = ""
            nuances = ""

        goal_label = GOAL_LABELS.get(data["goal"], data["goal"])

        pace = data.get("pace", "slow")
        water = calculate_water_goal(data["weight"], data["goal"], pace, carbs)
        user_data = {
            "weight": data["weight"],
            "height": data["height"],
            "age": data["age"],
            "gender": data["gender"],
            "activity": data["lifestyle"],
            "goal": data["goal"],
            "target_weight": target_weight,
            "pace": pace,
            "calories_goal": cal,
            "protein_goal": prot,
            "fat_goal": fat,
            "carbs_goal": carbs,
            "water_goal": water,
            "username": message.from_user.username,
            "last_activity_at": datetime.now(),
        }
        await save_user(message.from_user.id, user_data)
        await state.clear()

        text = (
            f"✅ <b>Профиль сохранён!</b>\n\n"
            f"🎯 Цель: {goal_label}\n"
            f"🏁 Желаемый вес: {target_weight or '—'} кг\n\n"
            f"<b>Расчёт:</b>\n"
            f"🔬 BMR (базовый обмен): {bmr} ккал\n"
            f"⚡ TDEE (расход в день): {tdee} ккал\n\n"
            f"<b>Ежедневные цели:</b>\n"
            f"🔥 Калории: <b>{cal} ккал</b>\n"
            f"🥩 Белки: <b>{prot} г</b> ({prot*4} ккал)\n"
            f"🧈 Жиры: <b>{fat} г</b> ({fat*9} ккал)\n"
            f"🍞 Углеводы: <b>{carbs} г</b> ({carbs*4} ккал)\n"
            f"💧 Вода: <b>{water} мл</b>\n"
        )
        if comment:
            text += f"\n💬 <i>{comment}</i>"
        if nuances:
            text += f"\n\n⚠️ <i>{nuances}</i>"
        text += "\n\nТеперь можно добавлять еду! 📷"

        await message.answer(text, parse_mode="HTML")
        await message.answer("👇 Меню:", reply_markup=main_keyboard())
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
        await log_weight(message.from_user.id, weight)
        await state.clear()

        user = await get_user(message.from_user.id)
        text = f"✅ Вес <b>{weight} кг</b> записан!"

        # Пересчёт целей КБЖУ и воды с учётом нового веса
        if user and user.get("height") and user.get("calories_goal") is not None:
            goal = user.get("goal") or "maintain"
            goal_key = goal if goal in ("loss", "gain", "maintain", "cutting", "recomp") else "maintain"
            pace = user.get("pace") or "slow"
            result = calculate_goals_ai(
                weight=weight,
                height=user["height"],
                age=user["age"],
                gender=user["gender"],
                lifestyle=user.get("activity") or "light",
                training_count=user.get("training_count") or "3",
                training_type=user.get("training_type") or "mixed",
                training_duration=user.get("training_duration") or "45",
                goal=goal,
                pace=pace,
                target_weight=user.get("target_weight"),
            )
            if result:
                cal = result["calories"]
                prot = result["protein"]
                fat = result["fat"]
                carbs = result["carbs"]
            else:
                cal, prot, fat, carbs = calculate_goals(
                    weight, user["height"], user["age"],
                    user["gender"], user.get("activity") or "sedentary", goal_key
                )
            water = calculate_water_goal(weight, goal, pace, carbs)
            updates = {k: user[k] for k in user if k != "user_id"}
            updates.update({
                "weight": weight,
                "calories_goal": cal,
                "protein_goal": prot,
                "fat_goal": fat,
                "carbs_goal": carbs,
                "water_goal": water,
                "username": message.from_user.username,
            })
            await save_user(message.from_user.id, updates)
            text += f"\n\n🔄 Цели пересчитаны под новый вес:\n🔥 {cal} ккал · 🥩 {prot} г · 🧈 {fat} г · 🍞 {carbs} г · 💧 {water} мл"

        if user and user.get("target_weight"):
            diff = abs(weight - user["target_weight"])
            arrow = "осталось до цели" if weight > user["target_weight"] else "ниже цели на"
            text += f"\n📍 {arrow}: <b>{diff:.1f} кг</b>"

        await message.answer(text, parse_mode="HTML")
    except ValueError:
        await message.answer("Введи число, например: 74.5")

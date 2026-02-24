from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_quick_foods, add_quick_food, delete_quick_food, add_meal, get_user, get_daily_totals
from keyboards import quick_foods_keyboard, main_keyboard
from calculator import format_daily_summary
from gemini_helper import analyze_food_text, analyze_food_photo
from reminders import check_goal_reached_and_send

router = Router()

class QuickState(StatesGroup):
    adding_name = State()

@router.message(F.text == "⚡ Быстрое добавление")
async def quick_menu(message: Message):
    foods = await get_quick_foods(message.from_user.id)
    if not foods:
        await message.answer(
            "⚡ <b>Быстрое добавление</b>\n\n"
            "У тебя пока нет быстрых продуктов.\n"
            "Нажми ➕ чтобы добавить частые продукты — например <i>Протеин 23г белка</i>",
            parse_mode="HTML",
            reply_markup=quick_foods_keyboard([])
        )
    else:
        await message.answer(
            "⚡ <b>Быстрое добавление</b>\nВыбери продукт:",
            parse_mode="HTML",
            reply_markup=quick_foods_keyboard(foods)
        )

@router.callback_query(F.data.startswith("quick_add_"))
async def quick_add(callback: CallbackQuery):
    food_id = int(callback.data.replace("quick_add_", ""))
    user_id = callback.from_user.id
    foods = await get_quick_foods(user_id)
    food = next((f for f in foods if f[0] == food_id), None)

    if not food:
        await callback.answer("Продукт не найден.")
        return

    fid, name, cal, p, f, c = food
    await add_meal(user_id, name, cal, p, f, c)

    user = await get_user(user_id)
    totals = await get_daily_totals(user_id)

    await callback.answer(f"✅ {name} добавлено!")

    if user:
        summary = format_daily_summary(totals, user)
        await callback.message.answer(f"✅ <b>{name}</b> добавлено!\n\n{summary}", parse_mode="HTML")

    await check_goal_reached_and_send(user_id, callback.bot)

@router.callback_query(F.data == "quick_new")
async def quick_new(callback: CallbackQuery, state: FSMContext):
    await state.set_state(QuickState.adding_name)
    await state.set_data({})  # сброс photo_file_id при новом добавлении
    await callback.message.answer(
        "Напиши название и количество <b>или отправь фото</b> блюда/упаковки.\n\n"
        "Примеры текстом:\n"
        "<i>Протеин KFD 30г</i>\n"
        "<i>Яйцо вареное 2шт</i>\n"
        "<i>Банан средний</i>",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(QuickState.adding_name)
async def quick_analyze(message: Message, state: FSMContext):
    data = await state.get_data()
    photo_file_id = data.get("quick_photo_file_id")

    # Ответ на уточнение по фото
    if photo_file_id and message.text:
        await message.answer("🔍 Пересматриваю фото с твоим уточнением...")
        try:
            file = await message.bot.get_file(photo_file_id)
            file_bytes = await message.bot.download_file(file.file_path)
            image_data = file_bytes.read()
        except Exception as e:
            print(f"Quick add: download photo for clarification: {e}")
            await message.answer("❌ Не удалось загрузить фото. Попробуй отправить заново.")
            return
        result = analyze_food_photo(image_data, caption=message.text.strip())
        await state.update_data(quick_photo_file_id=None)
        if not result or result.get("needs_clarification"):
            await message.answer("❌ Всё равно не вышло. Добавь текстом, например: <i>рис 200г</i>", parse_mode="HTML")
            return
        await _add_quick_food_from_result(message, state, result)
        return

    # Фото (новое или без уточнения)
    if message.photo:
        await message.answer("🔍 Считаю КБЖУ по фото...")
        photo = message.photo[-1]
        try:
            file = await message.bot.get_file(photo.file_id)
            file_bytes = await message.bot.download_file(file.file_path)
            image_data = file_bytes.read()
        except Exception as e:
            print(f"Quick add: download photo: {e}")
            await message.answer("❌ Не удалось загрузить фото. Попробуй ещё раз.")
            return
        result = analyze_food_photo(image_data, caption=message.caption)

        if not result:
            await message.answer("❌ Не смог распознать еду на фото. Напиши текстом, например: <i>овсянка 50г</i>", parse_mode="HTML")
            return
        if result.get("needs_clarification"):
            await state.update_data(quick_photo_file_id=photo.file_id)
            await message.answer(
                f"🤔 {result['question']}\n\nОтветь в следующем сообщении — пересмотрю фото с учётом этого.",
                parse_mode="HTML"
            )
            return
        await _add_quick_food_from_result(message, state, result)
        return

    # Текст
    if not message.text or not message.text.strip():
        await message.answer("Отправь текст (название и количество) или фото блюда.")
        return
    await message.answer("🔍 Считаю КБЖУ...")
    result = analyze_food_text(message.text.strip())

    if not result:
        await message.answer("❌ Не смог обработать. Попробуй иначе.")
        await state.clear()
        return

    await _add_quick_food_from_result(message, state, result)


async def _add_quick_food_from_result(message: Message, state: FSMContext, result: dict):
    await state.clear()
    await add_quick_food(
        message.from_user.id,
        result["name"],
        result["calories"],
        result["protein"],
        result["fat"],
        result["carbs"]
    )
    await message.answer(
        f"✅ <b>{result['name']}</b> добавлен в быстрые!\n"
        f"🔥 {result['calories']} ккал | Б:{result['protein']}г Ж:{result['fat']}г У:{result['carbs']}г",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "quick_delete")
async def quick_delete_menu(callback: CallbackQuery):
    foods = await get_quick_foods(callback.from_user.id)
    if not foods:
        await callback.answer("Нечего удалять.")
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = [[InlineKeyboardButton(text=f"❌ {f[1]}", callback_data=f"quick_del_{f[0]}")] for f in foods]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="quick_back")])
    await callback.message.edit_text("Выбери что удалить:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@router.callback_query(F.data.startswith("quick_del_"))
async def quick_del_confirm(callback: CallbackQuery):
    food_id = int(callback.data.replace("quick_del_", ""))
    await delete_quick_food(food_id, callback.from_user.id)
    await callback.answer("Удалено!")

    foods = await get_quick_foods(callback.from_user.id)
    await callback.message.edit_text(
        "⚡ <b>Быстрое добавление</b>\nВыбери продукт:",
        parse_mode="HTML",
        reply_markup=quick_foods_keyboard(foods)
    )

@router.callback_query(F.data == "quick_back")
async def quick_back(callback: CallbackQuery):
    foods = await get_quick_foods(callback.from_user.id)
    await callback.message.edit_text(
        "⚡ <b>Быстрое добавление</b>\nВыбери продукт:",
        parse_mode="HTML",
        reply_markup=quick_foods_keyboard(foods)
    )
    await callback.answer()

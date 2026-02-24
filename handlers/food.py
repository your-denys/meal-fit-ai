from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import add_meal, get_user, get_daily_totals
from gemini_helper import analyze_food_photo, analyze_food_text, get_daily_tip
from reminders import check_goal_reached_and_send
from keyboards import main_keyboard, confirm_food_keyboard
from calculator import format_daily_summary

router = Router()

class FoodState(StatesGroup):
    waiting_confirm = State()
    waiting_correction = State()
    waiting_clarification = State()

@router.message(F.text == "📷 Добавить еду")
async def add_food_prompt(message: Message):
    await message.answer(
        "📷 Отправь фото еды или упаковки\n"
        "📝 Или напиши текстом, например: <i>гречка с курицей 300г</i>",
        parse_mode="HTML"
    )

@router.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    await message.answer("🔍 Анализирую фото...")

    photo = message.photo[-1]
    bot = message.bot
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    image_data = file_bytes.read()

    result = analyze_food_photo(image_data, caption=message.caption)

    if not result and message.caption:
        result = analyze_food_text(message.caption.strip())

    if not result:
        await message.answer("❌ Не удалось распознать еду. Попробуй ещё раз или опиши текстом.")
        return
    if result.get("needs_clarification"):
        await state.update_data(food=result, photo_file_id=photo.file_id)
        await state.set_state(FoodState.waiting_clarification)
        await message.answer(f"🤔 {result['question']}\n\nОтветь текстом в следующем сообщении — пересмотрю фото с учётом твоего уточнения.")
        return

    await state.update_data(food=result, photo_file_id=photo.file_id)
    await state.set_state(FoodState.waiting_confirm)

    await message.answer(
        f"🍽 <b>{result['name']}</b>\n\n"
        f"🔥 Калории: <b>{result['calories']} ккал</b>\n"
        f"🥩 Белки: {result['protein']} г\n"
        f"🧈 Жиры: {result['fat']} г\n"
        f"🍞 Углеводы: {result['carbs']} г\n\n"
        f"💬 {result.get('comment', '')}\n\n"
        f"Всё верно?",
        parse_mode="HTML",
        reply_markup=confirm_food_keyboard()
    )

@router.message(FoodState.waiting_clarification)
async def handle_clarification(message: Message, state: FSMContext):
    data = await state.get_data()
    photo_file_id = data.get("photo_file_id")
    if photo_file_id:
        await message.answer("🔍 Пересматриваю фото с твоим уточнением...")
        try:
            bot = message.bot
            file = await bot.get_file(photo_file_id)
            file_bytes = await bot.download_file(file.file_path)
            image_data = file_bytes.read()
        except Exception as e:
            print(f"Download photo for clarification: {e}")
            image_data = None
        if image_data:
            result = analyze_food_photo(image_data, caption=message.text)
            if result and not result.get("needs_clarification"):
                await state.update_data(food=result)
                await state.set_state(FoodState.waiting_confirm)
                await message.answer(
                    f"🍽 <b>{result['name']}</b>\n\n"
                    f"🔥 Калории: <b>{result['calories']} ккал</b>\n"
                    f"🥩 Белки: {result['protein']} г\n"
                    f"🧈 Жиры: {result['fat']} г\n"
                    f"🍞 Углеводы: {result['carbs']} г\n\n"
                    f"💬 {result.get('comment', '')}\n\n"
                    f"Всё верно?",
                    parse_mode="HTML",
                    reply_markup=confirm_food_keyboard()
                )
                return
    original_text = data.get("original_food_text", "")
    original = data.get("food", {})
    original_name = original.get("name", "")
    full_prompt = f"Пользователь хотел добавить: '{original_text}'. Распознано как '{original_name}'. Пользователь уточняет: '{message.text}'. Рассчитай итоговое КБЖУ с учётом контекста."
    result = analyze_food_text(full_prompt)
    if not result or result.get("needs_clarification"):
        result = analyze_food_text(full_prompt, no_clarification=True)
    if not result or result.get("needs_clarification"):
        await state.clear()
        await message.answer("❌ Не удалось посчитать. Попробуй написать иначе.")
        return

    await state.update_data(food=result)
    await state.set_state(FoodState.waiting_confirm)
    await message.answer(
        f"🍽 <b>{result['name']}</b>\n\n"
        f"🔥 Калории: <b>{result['calories']} ккал</b>\n"
        f"🥩 Белки: {result['protein']} г\n"
        f"🧈 Жиры: {result['fat']} г\n"
        f"🍞 Углеводы: {result['carbs']} г\n\n"
        f"💬 {result.get('comment', '')}\n\n"
        f"Всё верно?",
        parse_mode="HTML",
        reply_markup=confirm_food_keyboard()
    )

@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_food(message: Message, state: FSMContext):
    current_state = await state.get_state()

    # Пропускаем если идёт онбординг или другой диалог
    if current_state and current_state not in [
        FoodState.waiting_correction.state,
        FoodState.waiting_clarification.state,
    ]:
        return

    data = await state.get_data()
    photo_file_id = data.get("photo_file_id") if current_state == FoodState.waiting_correction.state else None

    if photo_file_id:
        await message.answer("🔍 Пересматриваю фото с твоей правкой...")
        try:
            file = await message.bot.get_file(photo_file_id)
            file_bytes = await message.bot.download_file(file.file_path)
            image_data = file_bytes.read()
            result = analyze_food_photo(image_data, caption=message.text)
        except Exception as e:
            print(f"Download photo for correction: {e}")
            result = None
        if not result:
            result = analyze_food_text(message.text)
    else:
        await message.answer("🔍 Считаю КБЖУ...")
        result = analyze_food_text(message.text)
    if not result:
        await message.answer("❌ Не смог обработать. Попробуй написать иначе, например: <i>куриная грудка 200г</i>", parse_mode="HTML")
        return
    if result.get("needs_clarification"):
        await state.update_data(original_food_text=message.text, food=result)
        await state.set_state(FoodState.waiting_clarification)
        await message.answer(f"🤔 {result['question']}")
        return
    await state.update_data(food=result)
    await state.set_state(FoodState.waiting_confirm)
    await message.answer(
        f"🍽 <b>{result['name']}</b>\n\n"
        f"🔥 Калории: <b>{result['calories']} ккал</b>\n"
        f"🥩 Белки: {result['protein']} г\n"
        f"🧈 Жиры: {result['fat']} г\n"
        f"🍞 Углеводы: {result['carbs']} г\n\n"
        f"💬 {result.get('comment', '')}\n\n"
        f"Всё верно?",
        parse_mode="HTML",
        reply_markup=confirm_food_keyboard()
    )

@router.callback_query(F.data == "food_confirm", FoodState.waiting_confirm)
async def food_confirmed(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    food = data["food"]
    user_id = callback.from_user.id

    await add_meal(user_id, food["name"], food["calories"], food["protein"], food["fat"], food["carbs"])
    await state.clear()

    user = await get_user(user_id)
    totals = await get_daily_totals(user_id)

    await callback.message.edit_text(f"✅ <b>{food['name']}</b> добавлено!", parse_mode="HTML")

    if user:
        summary = format_daily_summary(totals, user)
        tip = get_daily_tip(totals, user)
        text = summary
        if tip:
            text += f"\n\n💡 {tip}"
        await callback.message.answer(text, parse_mode="HTML")

    await check_goal_reached_and_send(user_id, callback.bot)
    await callback.answer()

@router.callback_query(F.data == "food_edit", FoodState.waiting_confirm)
async def food_edit(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FoodState.waiting_correction)
    await callback.message.edit_text("✏️ Напиши как правильно, например: <i>борщ 400г</i>", parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "food_cancel")
async def food_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()

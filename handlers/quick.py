from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_quick_foods, add_quick_food, delete_quick_food, add_meal, get_user, get_daily_totals
from keyboards import quick_foods_keyboard, main_keyboard
from calculator import format_daily_summary
from gemini_helper import analyze_food_text

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

@router.callback_query(F.data == "quick_new")
async def quick_new(callback: CallbackQuery, state: FSMContext):
    await state.set_state(QuickState.adding_name)
    await callback.message.answer(
        "Напиши название и количество, например:\n"
        "<i>Протеин KFD 30г</i>\n"
        "<i>Яйцо вареное 2шт</i>\n"
        "<i>Банан средний</i>",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(QuickState.adding_name)
async def quick_analyze(message: Message, state: FSMContext):
    await message.answer("🔍 Считаю КБЖУ...")
    result = analyze_food_text(message.text)

    if not result:
        await message.answer("❌ Не смог обработать. Попробуй иначе.")
        await state.clear()
        return

    await add_quick_food(
        message.from_user.id,
        result["name"],
        result["calories"],
        result["protein"],
        result["fat"],
        result["carbs"]
    )
    await state.clear()

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

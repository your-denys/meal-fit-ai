from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📷 Добавить еду"), KeyboardButton(text="🍽 Сегодня")],
            [KeyboardButton(text="💡 Что съесть?"), KeyboardButton(text="⚡ Быстрое добавление")],
            [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="🏆 Результаты")],
            [KeyboardButton(text="⚖️ Записать вес"), KeyboardButton(text="📖 Что я умею")],
        ],
        resize_keyboard=True
    )


def meal_choice_keyboard():
    """Клавиатура выбора приёма пищи для совета «Что съесть?»."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌅 Завтрак", callback_data="meal_breakfast"),
            InlineKeyboardButton(text="☀️ Обед", callback_data="meal_lunch"),
        ],
        [
            InlineKeyboardButton(text="🌙 Ужин", callback_data="meal_dinner"),
            InlineKeyboardButton(text="🍎 Перекус", callback_data="meal_snack"),
        ],
    ])

def confirm_food_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Верно", callback_data="food_confirm"),
            InlineKeyboardButton(text="✏️ Исправить", callback_data="food_edit"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="food_cancel")]
    ])

def stats_keyboard():
    """Клавиатура в разделе «📊 Статистика»: неделя, месяц, список веса."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📆 Неделя", callback_data="stats_week"),
            InlineKeyboardButton(text="🗓 Месяц", callback_data="stats_month"),
        ],
        [InlineKeyboardButton(text="⚖️ Список веса", callback_data="stats_weight")],
    ])

def quick_foods_keyboard(foods: list):
    buttons = []
    for food in foods:
        fid, name, cal, p, f, c = food
        buttons.append([InlineKeyboardButton(
            text=f"{name} ({cal} ккал)",
            callback_data=f"quick_add_{fid}"
        )])
    buttons.append([
        InlineKeyboardButton(text="➕ Добавить быстрое", callback_data="quick_new"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data="quick_delete"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def activity_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪑 Сидячий", callback_data="activity_sedentary")],
        [InlineKeyboardButton(text="🚶 Немного активный", callback_data="activity_light")],
        [InlineKeyboardButton(text="🏃 Активный", callback_data="activity_moderate")],
        [InlineKeyboardButton(text="💪 Очень активный", callback_data="activity_high")],
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

def gender_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👨 Мужской", callback_data="gender_male"),
            InlineKeyboardButton(text="👩 Женский", callback_data="gender_female"),
        ]
    ])

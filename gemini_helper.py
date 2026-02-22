import google.generativeai as genai
import json
import re
from config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

SYSTEM_PROMPT = """Ты нутрициолог-ассистент. Твоя задача — оценить КБЖУ еды.
Всегда отвечай ТОЛЬКО валидным JSON без лишнего текста.
Формат ответа:
{
  "name": "название блюда",
  "calories": 000,
  "protein": 00.0,
  "fat": 00.0,
  "carbs": 00.0,
  "comment": "короткий комментарий"
}
Оценивай реалистично. Если на фото несколько блюд — суммируй всё."""

def analyze_food_photo(image_bytes: bytes, mime_type: str = "image/jpeg", caption: str = None) -> dict | None:
    try:
        if caption:
            prompt = f"{SYSTEM_PROMPT}\n\nПользователь уточнил: {caption}\nОцени КБЖУ с учётом этого уточнения."
        else:
            prompt = SYSTEM_PROMPT
        response = model.generate_content([
            prompt,
            {"mime_type": mime_type, "data": image_bytes}
        ])
        text = response.text.strip()
        text = re.sub(r"```json|```", "", text).strip()
        return json.loads(text)
    except Exception as e:
        print(f"Gemini photo error: {e}")
        return None

def calculate_goals_ai(weight, height, age, gender, lifestyle, training_count, training_type, training_duration, goal, pace="slow", target_weight=None) -> dict | None:
    gender_ru = "мужчина" if gender == "male" else "женщина"

    lifestyle_labels = {
        "sedentary": "сидячий образ жизни, минимум движения вне тренировок",
        "light": "среднеактивный (много ходит, стоячая работа)",
        "active": "физически активный (физический труд)",
    }

    training_type_labels = {
        "strength": "силовые тренировки",
        "cardio": "кардио тренировки",
        "mixed": "смешанные (силовые + кардио)",
        "none": "без тренировок",
    }

    pace_labels = {
        "slow": "медленный темп (комфортный, без стресса для организма)",
        "fast": "быстрый темп (агрессивный режим, строгий дефицит/профицит)",
    }

    goal_instructions = {
        "loss": "ПОХУДЕНИЕ. Дефицит калорий. Белок высокий (1.8-2.2 г/кг).",
        "gain": "НАБОР МАССЫ. Профицит калорий. Белок высокий (1.8-2.2 г/кг). Углеводы высокие.",
        "maintain": "ПОДДЕРЖАНИЕ. Калории = TDEE. Белок: если человек тренируется 3+ раз в неделю (особенно силово) — 1.8-2.2 г/кг; если нет тренировок — 1.4-1.6 г/кг. Учитывай улучшение композиции тела при желаемом весе близком к текущему.",
        "recomp": "РЕКОМПОЗИЦИЯ. Калории на уровне TDEE (без дефицита и профицита). Белок высокий (1.8–2.2 г/кг) для сохранения/набора мышечной массы при сжигании жира. Углеводы и жиры умеренно. Цель — улучшение состава тела при стабильном весе.",
        "cutting": "СУШКА. Дефицит калорий. Белок высокий (2-2.5 г/кг). Углеводы ниже, жиры умеренно.",
    }

    if goal in goal_instructions:
        goal_text = goal_instructions[goal]
    else:
        goal_text = f"Цель пользователя: {goal}. Подбери оптимальные КБЖУ."

    target_text = f"Желаемый вес: {target_weight} кг (разница {target_weight - weight:+.1f} кг)." if target_weight else "Желаемый вес не указан."

    training_info = (
        f"Без тренировок." if training_count == "0"
        else f"{training_count} раз/нед, тип: {training_type_labels.get(training_type, training_type)}, длительность: {training_duration} мин."
    )

    prompt = f"""Ты опытный нутрициолог и диетолог. Рассчитай персональные цели КБЖУ на день.

Данные клиента:
- Пол: {gender_ru} (обязательно учитывай при расчёте BMR)
- Возраст: {age} лет
- Текущий вес: {weight} кг
- Рост: {height} см
- Образ жизни вне тренировок: {lifestyle_labels.get(lifestyle, lifestyle)}
- Тренировки: {training_info}
- {target_text}
- Желаемый темп: {pace_labels.get(pace, pace)}

Формула BMR Миффлина-Сан Жеора (применяй строго по полу):
• Для мужчины: BMR = 10×вес(кг) + 6.25×рост(см) − 5×возраст + 5
• Для женщины: BMR = 10×вес(кг) + 6.25×рост(см) − 5×возраст − 161
У женщины BMR всегда ниже при тех же росте/весе/возрасте — не путай формулы.

Задача: {goal_text}

ВАЖНО — расчёт для тренирующегося, а не «универсальный диетологический»:
• Если тренировки 3–4 раза в неделю (особенно силовые/смешанные): белок не ниже 1.8 г/кг, при 4 силовых — целевой диапазон 2–2.2 г/кг. Не используй минимум 1.4–1.5 г/кг для таких людей.
• Жиры: не фиксируй шаблонные 28%. Считай от 0.8–1 г/кг или 25–30% в зависимости от цели; при наборе можно выше, при сушке — умеренно.
• TDEE: 3–4 силовые в неделю = активность выше «умеренной» (коэффициент 1.55–1.725 в зависимости от количества и длительности).
• При цели «поддержание» и желаемом весе близком к текущему (рекомпозиция): калории = TDEE, но белок высокий (1.8–2.2 г/кг), чтобы поддерживать мышцы и композицию.

Темп задаёт отклонение от TDEE:
• Медленный темп: дефицит 250–400 ккал (сушка/похудение) или профицит 200–300 ккал (набор массы).
• Быстрый темп: дефицит 450–600 ккал (сушка/похудение) или профицит 350–500 ккал (набор массы).
• Поддержание (maintain): калории = TDEE, без дефицита и профицита.
Сушка — более строгий дефицит и высокий белок (сохранить мышцы). Похудение — умеренный дефицит.

Рассчитай пошагово:
1. BMR по формуле Миффлина-Сан Жеора именно для пола клиента (см. формулы выше)
2. TDEE с учётом образа жизни И тренировок
3. Скорректируй под цель и темп
4. Раздели на макросы

Ответь ТОЛЬКО валидным JSON без лишнего текста, без markdown:
{{
  "bmr": 0000,
  "tdee": 0000,
  "calories": 0000,
  "protein": 000,
  "fat": 00,
  "carbs": 000,
  "comment": "2-3 предложения: как получились цифры, какой коэффициент активности и почему (если 3-4 тренировки — укажи что учтены силовые и белок для тренирующегося), при поддержании с целевым весом — можно упомянуть рекомпозицию",
  "nuances": "важные нюансы и рекомендации если есть, иначе пустая строка"
}}

Все поля обязательны. bmr и tdee должны быть числами, не строками."""

    try:
        response = model.generate_content(prompt)
        text_resp = response.text.strip()
        text_resp = re.sub(r"```json|```", "", text_resp).strip()
        data = json.loads(text_resp)
        # Гарантированно правильный BMR по полу (модель иногда путает мужскую/женскую формулу)
        bmr_correct = _bmr_mifflin_st_jeor(weight, height, age, gender)
        old_bmr, old_tdee = data.get("bmr"), data.get("tdee")
        deficit = (data["calories"] - old_tdee) if (data.get("calories") is not None and old_tdee) else 0
        data["bmr"] = round(bmr_correct)
        if old_tdee and old_bmr:
            mult = old_tdee / max(old_bmr, 1)
            data["tdee"] = round(bmr_correct * mult)
        if data.get("calories") is not None and data.get("tdee") is not None:
            data["calories"] = round(data["tdee"] + deficit)
            p, f = data.get("protein", 0), data.get("fat", 0)
            if p is not None and data["calories"]:
                data["carbs"] = max(0, round((data["calories"] - p * 4 - f * 9) / 4))
        return data
    except Exception as e:
        print(f"Gemini goals error: {e}")
        return None


def _bmr_mifflin_st_jeor(weight: float, height: float, age: int, gender: str) -> float:
    """BMR по формуле Миффлина-Сан Жеора. gender: 'male' или 'female'."""
    base = 10 * weight + 6.25 * height - 5 * age
    return base + 5 if gender == "male" else base - 161

def analyze_food_text(text: str) -> dict | None:
    try:
        prompt = f"{SYSTEM_PROMPT}\n\nПользователь написал: {text}\nОцени КБЖУ для этого."
        response = model.generate_content(prompt)
        result = response.text.strip()
        result = re.sub(r"```json|```", "", result).strip()
        return json.loads(result)
    except Exception as e:
        print(f"Gemini text error: {e}")
        return None


def get_daily_tip(totals: dict, user: dict) -> str | None:
    goal = user.get("goal", "")
    cal_goal = user.get("calories_goal", 0)
    prot_goal = user.get("protein_goal", 0)
    carb_goal = user.get("carbs_goal", 0)

    if not cal_goal:
        return None

    cal_pct = totals["calories"] / cal_goal * 100
    prot_pct = totals["protein"] / prot_goal * 100 if prot_goal else 0
    carb_pct = totals["carbs"] / carb_goal * 100 if carb_goal else 0

    goal_labels = {
        "loss": "похудение",
        "gain": "набор массы",
        "maintain": "поддержание",
        "recomp": "рекомпозиция",
        "cutting": "сушка",
    }

    prompt = f"""Ты нутрициолог-ассистент. Дай короткий практический совет (1 предложение) на основе данных.

Цель пользователя: {goal_labels.get(goal, goal)}
Прогресс за сегодня:
- Калории: {totals['calories']}/{cal_goal} ккал ({cal_pct:.0f}%)
- Белки: {totals['protein']:.0f}/{prot_goal} г ({prot_pct:.0f}%)
- Углеводы: {totals['carbs']:.0f}/{carb_goal} г ({carb_pct:.0f}%)

Правила:
- Если превышение калорий > 90% — предупреди
- Если белка < 50% к вечеру — напомни добрать
- Для сушки — следи за углеводами
- Для набора — следи за калориями и белком
- Для рекомпозиции — калории на уровне цели, белок в приоритете
- Если всё хорошо — скажи коротко что всё идёт по плану
- Только 1 предложение, без приветствий"""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini tip error: {e}")
        return None


MEAL_TYPE_LABELS = {
    "завтрак": "завтрак",
    "обед": "обед",
    "ужин": "ужин",
    "перекус": "перекус",
}


def get_meal_suggestion(totals: dict, user: dict, meal_type: str, eaten_today: list[str] | None = None) -> str | None:
    """Совет что съесть на выбранный приём пищи с учётом цели и текущих КБЖУ за день."""
    cal_goal = user.get("calories_goal", 0)
    prot_goal = user.get("protein_goal", 0)
    fat_goal = user.get("fat_goal", 0)
    carb_goal = user.get("carbs_goal", 0)
    goal = user.get("goal", "")

    if not cal_goal:
        return None

    goal_labels = {
        "loss": "похудение",
        "gain": "набор массы",
        "maintain": "поддержание",
        "recomp": "рекомпозиция",
        "cutting": "сушка",
    }
    meal_label = MEAL_TYPE_LABELS.get(meal_type, meal_type)

    cal_rem = cal_goal - totals["calories"]
    prot_rem = prot_goal - totals["protein"]
    fat_rem = fat_goal - totals["fat"]
    carb_rem = carb_goal - totals["carbs"]

    eaten_block = ""
    if eaten_today:
        eaten_block = f"\nУже ели сегодня: {', '.join(eaten_today)}. Не предлагай те же блюда и тот же основной белок — выбери другой вариант."

    prompt = f"""Ты нутрициолог-ассистент. Пользователь просит совет: что съесть на {meal_label}.

Цель пользователя: {goal_labels.get(goal, goal)}
Цели на день: {cal_goal} ккал, белки {prot_goal} г, жиры {fat_goal} г, углеводы {carb_goal} г.
Уже съедено за сегодня: {totals['calories']} ккал, Б {totals['protein']:.0f} г, Ж {totals['fat']:.0f} г, У {totals['carbs']:.0f} г.
Осталось (или перебор): калории {cal_rem:+d}, белок {prot_rem:+.0f} г, жиры {fat_rem:+.0f} г, углеводы {carb_rem:+.0f} г.{eaten_block}

Разнообразие обязательно: не предлагай каждый раз куриную грудку. Чередуй источники белка — рыба (лосось, треска, минтай, скумбрия), индейка, яйца/омлет, творог, бобовые (чечевица, нут, фасоль), морепродукты (креветки, кальмары), говядина/телятина, субпродукты. Разные кухни и способы приготовления (запечённое, на пару, тушёное, салат, суп, паста с морепродуктами и т.д.). Один вариант — одно блюдо, без перечисления пяти альтернатив.{' Для перекуса предлагай только простое: фрукты, творог, йогурт, орехи, сэндвич/тост, банан с орехами, смузи, сыр — без запечённого картофеля, батата и сложных блюд (то, что готовят к обеду/ужину).' if meal_type == 'перекус' else ''}

Ответь коротко и по делу, в трёх блоках — обычным текстом, без звёздочек и разметки (ни ** ни *):
1) Блюдо: 
[конкретное блюдо/продукты + примерная порция]
2) Что добрать: 
[одним абзацем — калории/белок/жиры/углеводы; если перебор — что ограничить]
3) Почему это блюдо: 
[1–2 предложения]

Без общих фраз, только по цифрам. Не используй markdown — только переносы строк и цифры. Пиши на русском."""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Убрать markdown-звёздочки, чтобы в Telegram не светились ** и *
        text = text.replace("**", "").replace("* ", "• ").replace("*", "•")
        return text
    except Exception as e:
        print(f"Gemini meal suggestion error: {e}")
        return None


def get_reminder_suggestion(
    totals: dict,
    user: dict,
    eaten_today: list[str],
    hour: int,
    last_meal_minutes_ago: int | None = None,
    last_meal_name: str | None = None,
) -> str | None:
    """
    Короткое напоминание «пора поесть» с учётом недобора, всего рациона за день и времени последнего приёма.
    """
    cal_goal = user.get("calories_goal", 0) or 1
    prot_goal = user.get("protein_goal", 0) or 1
    carb_goal = user.get("carbs_goal", 0) or 1
    cal_rem = cal_goal - totals["calories"]
    prot_rem = prot_goal - totals["protein"]
    carb_rem = carb_goal - totals["carbs"]

    if cal_rem < 30 and prot_rem < 5 and carb_rem < 10:
        return None

    goal_labels = {"loss": "похудение", "gain": "набор массы", "maintain": "поддержание", "recomp": "рекомпозиция", "cutting": "сушка"}
    goal = goal_labels.get(user.get("goal", ""), user.get("goal", ""))

    time_context = ""
    if hour < 10:
        time_context = "Раннее утро: предложи лёгкий завтрак или перекус, без огромных порций белка."
    elif hour < 14:
        time_context = "День: можно полноценный приём пищи или перекус с белком и углеводами."
    elif hour < 19:
        time_context = "Вторая половина дня: обед или перекус, конкретные порции."
    elif hour < 22:
        time_context = "Вечер: лёгкий перекус или ужин, не перегружай — до 22:00 ещё можно поесть нормально."
    else:
        time_context = "Поздний вечер (после 22): только очень лёгкий вариант (кефир, творог, фрукт), либо напиши что лучше поесть утром."

    eaten_block = f" Весь сегодняшний рацион (не повторяй эти блюда и похожие): {', '.join(eaten_today[:20])}." if eaten_today else ""
    last_meal_block = ""
    if last_meal_minutes_ago is not None and last_meal_name:
        last_meal_block = f" Последний приём был {last_meal_minutes_ago} мин назад («{last_meal_name}») — можно упомянуть в одном предложении, что прошло уже достаточно времени."

    prompt = f"""Ты нутрициолог. Напоминание пользователю «пора поесть» с учётом недобора и всего рациона за день.

Цель пользователя: {goal}.
Цели на день: {cal_goal} ккал, белки {prot_goal} г, углеводы {carb_goal} г.
Съедено за сегодня: {totals['calories']} ккал, Б {totals['protein']:.0f} г, У {totals['carbs']:.0f} г.
Недобор: калории {cal_rem:.0f}, белок {prot_rem:.0f} г, углеводы {carb_rem:.0f} г.{eaten_block}{last_meal_block}

Время: сейчас {hour}:00. {time_context}
Обязательно предлагай что-то другое по составу и продуктам, не повторяй уже съеденное сегодня.

Ответь коротко (2–4 предложения), в формате:
1) «Пора перекусить» / «Пора поесть» + что именно съесть (конкретно: порция и продукт, например «200 г творога + банан» или «омлет из 2 яиц + тост»).
2) Почему это восполнит недобор (какой макро/калории закроет).

Без приветствий и лишнего. Только суть. На русском."""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini reminder suggestion error: {e}")
        return None


def answer_user_question(context: str, user_message: str) -> str | None:
    """Ответ ИИ на вопрос пользователя в контексте сообщения бота (напоминание, совет и т.д.)."""
    if not context and not user_message:
        return None
    prompt = f"""Ты нутрициолог-ассистент в боте для учёта питания.

Контекст (сообщение, которое бот только что отправил пользователю):
{context or '(нет)'}

Вопрос или реплика пользователя:
{user_message}

Дай краткий ответ по существу (1–4 предложения), без приветствий. Если вопрос не по питанию — ответь коротко и дружелюбно."""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini answer_user_question error: {e}")
        return None

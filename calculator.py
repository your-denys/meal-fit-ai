def calculate_goals(weight, height, age, gender, activity, goal):
    """Mifflin-St Jeor formula"""
    if gender == "male":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    activity_multipliers = {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "high": 1.725,
    }
    tdee = bmr * activity_multipliers.get(activity, 1.2)

    if goal == "loss":
        calories = tdee - 400
    elif goal == "gain":
        calories = tdee + 300
    elif goal == "recomp":
        calories = tdee  # поддержание калорий, высокий белок — в формуле ниже
    else:
        calories = tdee

    calories = round(calories)
    protein = round(weight * 2.0) if goal == "recomp" else round(weight * 1.8)  # рекомпозиция: выше белок
    fat = round(calories * 0.25 / 9)    # 25% of calories
    carbs = round((calories - protein * 4 - fat * 9) / 4)

    return calories, protein, fat, carbs


def calculate_water_goal(weight_kg: float, goal: str, pace: str, carbs_g: float | int) -> int:
    """
    Суточная норма воды (мл) по цели и темпу.
    goal: maintain, loss, cutting, gain
    pace: slow = мягкая, fast = агрессивная
    """
    soft = pace in ("slow", None, "")
    if goal == "maintain" or goal == "recomp":
        base_ml_per_kg = 32.5   # 30–35
    elif goal == "loss":
        base_ml_per_kg = 35 if soft else 37.5   # 35 или 35–40
    elif goal == "cutting":
        base_ml_per_kg = 40 if soft else 42.5    # 40 или 40–45
    elif goal == "gain":
        base_ml_per_kg = 32.5 if soft else 37.5  # 30–35 или 35–40
    else:
        base_ml_per_kg = 32.5
    total = round(weight_kg * base_ml_per_kg)
    if carbs_g < 100:
        total += 300
    return total


def format_daily_summary(totals, user):
    return (
        f"📊 <b>Сегодня:</b>\n\n"
        f"🔥 Калории: {totals['calories']}/{user.get('calories_goal', '?')} ккал\n"
        f"🥩 Белки:   {totals['protein']:.1f}/{user.get('protein_goal', '?')} г\n"
        f"🧈 Жиры:    {totals['fat']:.1f}/{user.get('fat_goal', '?')} г\n"
        f"🍞 Углеводы: {totals['carbs']:.1f}/{user.get('carbs_goal', '?')} г"
    )

"""
PostgreSQL (Neon) через asyncpg. Пул создаётся в bot.py и передаётся в set_pool().
"""
import asyncpg
from datetime import date, datetime

_pool: asyncpg.Pool | None = None


def set_pool(pool: asyncpg.Pool):
    global _pool
    _pool = pool


def _get_pool():
    if _pool is None:
        raise RuntimeError("Database pool not set. Call database.set_pool(pool) at startup.")
    return _pool


async def init_db(pool: asyncpg.Pool | None = None):
    """Создать таблицы и опционально колонки. Вызывать с pool при старте бота."""
    p = pool or _get_pool()
    async with p.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                name TEXT,
                weight REAL,
                height REAL,
                age INTEGER,
                gender TEXT,
                activity TEXT,
                goal TEXT,
                target_weight REAL,
                calories_goal INTEGER,
                protein_goal INTEGER,
                fat_goal INTEGER,
                carbs_goal INTEGER,
                water_goal INTEGER,
                pace TEXT,
                reminders_enabled INTEGER DEFAULT 1,
                reminders_per_day INTEGER DEFAULT 3,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for col, typ in [("water_goal", "INTEGER"), ("pace", "TEXT")]:
            try:
                await conn.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
            except asyncpg.exceptions.DuplicateColumnError:
                pass

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reminder_log (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                sent_at TIMESTAMP,
                date DATE
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS meals (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                name TEXT,
                calories INTEGER,
                protein REAL,
                fat REAL,
                carbs REAL,
                date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS weight_log (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                weight REAL,
                date DATE
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS quick_foods (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                name TEXT,
                calories INTEGER,
                protein REAL,
                fat REAL,
                carbs REAL
            )
        """)


# --- Users ---

USER_KEYS = [
    "user_id", "name", "weight", "height", "age", "gender", "activity", "goal",
    "target_weight", "calories_goal", "protein_goal", "fat_goal", "carbs_goal", "water_goal", "pace",
    "reminders_enabled", "reminders_per_day", "created_at"
]


async def get_user(user_id: int):
    p = _get_pool()
    async with p.acquire() as conn:
        sel = ", ".join(USER_KEYS)
        row = await conn.fetchrow(f"SELECT {sel} FROM users WHERE user_id = $1", user_id)
    if row:
        return dict(row)
    return None


async def save_user(user_id: int, data: dict):
    p = _get_pool()
    async with p.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM users WHERE user_id = $1", user_id)
        if exists:
            n = len(data)
            sets = ", ".join(f"{k} = ${i+1}" for i, k in enumerate(data.keys()))
            await conn.execute(f"UPDATE users SET {sets} WHERE user_id = ${n+1}", *data.values(), user_id)
        else:
            data = {**data, "user_id": user_id}
            keys = ", ".join(data.keys())
            placeholders = ", ".join(f"${i+1}" for i in range(len(data)))
            await conn.execute(f"INSERT INTO users ({keys}) VALUES ({placeholders})", *data.values())


async def get_users_for_reminders():
    p = _get_pool()
    async with p.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id FROM users WHERE (reminders_enabled IS NULL OR reminders_enabled = 1) AND calories_goal IS NOT NULL AND calories_goal > 0"
        )
    return [r["user_id"] for r in rows]


async def log_reminder_sent(user_id: int):
    p = _get_pool()
    now = datetime.now()
    async with p.acquire() as conn:
        await conn.execute(
            "INSERT INTO reminder_log (user_id, sent_at, date) VALUES ($1, $2, $3)",
            user_id, now, now.date()
        )


async def get_reminder_count_today(user_id: int):
    today = date.today()
    p = _get_pool()
    async with p.acquire() as conn:
        n = await conn.fetchval("SELECT COUNT(*) FROM reminder_log WHERE user_id = $1 AND date = $2", user_id, today)
    return n


async def get_last_reminder_sent_at(user_id: int):
    today = date.today()
    p = _get_pool()
    async with p.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT sent_at FROM reminder_log WHERE user_id = $1 AND date = $2 ORDER BY sent_at DESC LIMIT 1",
            user_id, today
        )
    if not row or not row["sent_at"]:
        return None
    ts = row["sent_at"]
    return ts.replace(tzinfo=None) if getattr(ts, "tzinfo", None) else ts


# --- Meals ---

async def add_meal(user_id: int, name: str, calories: int, protein: float, fat: float, carbs: float):
    p = _get_pool()
    today = date.today()
    async with p.acquire() as conn:
        await conn.execute(
            "INSERT INTO meals (user_id, name, calories, protein, fat, carbs, date) VALUES ($1,$2,$3,$4,$5,$6,$7)",
            user_id, name, calories, protein, fat, carbs, today
        )


async def get_meals_today(user_id: int):
    p = _get_pool()
    today = date.today()
    async with p.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, calories, protein, fat, carbs FROM meals WHERE user_id = $1 AND date = $2 ORDER BY id",
            user_id, today
        )
    return [(r["id"], r["name"], r["calories"], r["protein"], r["fat"], r["carbs"]) for r in rows]


async def get_last_meal_today(user_id: int):
    p = _get_pool()
    today = date.today()
    async with p.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT created_at, name, calories FROM meals WHERE user_id = $1 AND date = $2 ORDER BY id DESC LIMIT 1",
            user_id, today
        )
    if not row:
        return None
    created = row["created_at"]
    if hasattr(created, "isoformat"):
        created = created.isoformat()
    return (str(created), row["name"], int(row["calories"] or 0))


async def delete_last_meal(user_id: int):
    p = _get_pool()
    today = date.today()
    async with p.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM meals WHERE user_id = $1 AND date = $2 ORDER BY id DESC LIMIT 1", user_id, today)
        if row:
            await conn.execute("DELETE FROM meals WHERE id = $1", row["id"])
            return True
    return False


async def delete_meal_by_id(meal_id: int, user_id: int):
    p = _get_pool()
    async with p.acquire() as conn:
        r = await conn.execute("DELETE FROM meals WHERE id = $1 AND user_id = $2", meal_id, user_id)
    return r == "DELETE 1"


async def get_daily_totals(user_id: int, target_date: date | None = None):
    p = _get_pool()
    d = target_date or date.today()
    async with p.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT SUM(calories) AS cal, SUM(protein) AS prot, SUM(fat) AS fat, SUM(carbs) AS carb FROM meals WHERE user_id = $1 AND date = $2",
            user_id, d
        )
    return {
        "calories": int(row["cal"] or 0),
        "protein": float(row["prot"] or 0),
        "fat": float(row["fat"] or 0),
        "carbs": float(row["carb"] or 0),
    }


async def get_meals_range(user_id: int, from_date: date, to_date: date):
    p = _get_pool()
    async with p.acquire() as conn:
        rows = await conn.fetch(
            """SELECT date::text AS d, SUM(calories) AS cal, SUM(protein) AS prot, SUM(fat) AS fat, SUM(carbs) AS carb
               FROM meals WHERE user_id = $1 AND date BETWEEN $2 AND $3 GROUP BY date ORDER BY date""",
            user_id, from_date, to_date
        )
    return [(r["d"], r["cal"] or 0, r["prot"] or 0, r["fat"] or 0, r["carb"] or 0) for r in rows]


# --- Weight ---

async def log_weight(user_id: int, weight: float):
    p = _get_pool()
    today = date.today()
    async with p.acquire() as conn:
        await conn.execute("INSERT INTO weight_log (user_id, weight, date) VALUES ($1,$2,$3)", user_id, weight, today)
        await conn.execute("UPDATE users SET weight = $1 WHERE user_id = $2", weight, user_id)


async def get_weight_history(user_id: int, limit: int = 30):
    p = _get_pool()
    async with p.acquire() as conn:
        rows = await conn.fetch(
            "SELECT weight, date FROM weight_log WHERE user_id = $1 ORDER BY date DESC LIMIT $2",
            user_id, limit
        )
    return [(r["weight"], r["date"].isoformat() if hasattr(r["date"], "isoformat") else str(r["date"])) for r in rows]


# --- Quick foods ---

async def get_quick_foods(user_id: int):
    p = _get_pool()
    async with p.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, calories, protein, fat, carbs FROM quick_foods WHERE user_id = $1", user_id)
    return [(r["id"], r["name"], r["calories"], r["protein"], r["fat"], r["carbs"]) for r in rows]


async def add_quick_food(user_id: int, name: str, calories: int, protein: float, fat: float, carbs: float):
    p = _get_pool()
    async with p.acquire() as conn:
        await conn.execute(
            "INSERT INTO quick_foods (user_id, name, calories, protein, fat, carbs) VALUES ($1,$2,$3,$4,$5,$6)",
            user_id, name, calories, protein, fat, carbs
        )


async def delete_quick_food(food_id: int, user_id: int):
    p = _get_pool()
    async with p.acquire() as conn:
        await conn.execute("DELETE FROM quick_foods WHERE id = $1 AND user_id = $2", food_id, user_id)

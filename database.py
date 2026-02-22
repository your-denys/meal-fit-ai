import sqlite3
from datetime import date

DB_PATH = "meal_fit.db"

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
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
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        c.execute("ALTER TABLE users ADD COLUMN water_goal INTEGER")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN pace TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN reminders_enabled INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN reminders_per_day INTEGER DEFAULT 3")
    except sqlite3.OperationalError:
        pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS reminder_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            sent_at TEXT,
            date TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            calories INTEGER,
            protein REAL,
            fat REAL,
            carbs REAL,
            date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS weight_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            weight REAL,
            date TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS quick_foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            calories INTEGER,
            protein REAL,
            fat REAL,
            carbs REAL
        )
    """)

    conn.commit()
    conn.close()

# --- Users ---

USER_KEYS = [
    "user_id", "name", "weight", "height", "age", "gender", "activity", "goal",
    "target_weight", "calories_goal", "protein_goal", "fat_goal", "carbs_goal", "water_goal", "pace",
    "reminders_enabled", "reminders_per_day", "created_at"
]

def get_user(user_id):
    conn = get_conn()
    c = conn.cursor()
    sel = ", ".join(USER_KEYS)
    c.execute(f"SELECT {sel} FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(zip(USER_KEYS, row))
    return None

def save_user(user_id, data: dict):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    exists = c.fetchone()
    if exists:
        sets = ", ".join(f"{k} = ?" for k in data.keys())
        c.execute(f"UPDATE users SET {sets} WHERE user_id = ?", (*data.values(), user_id))
    else:
        data["user_id"] = user_id
        keys = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        c.execute(f"INSERT INTO users ({keys}) VALUES ({placeholders})", list(data.values()))
    conn.commit()
    conn.close()


def get_users_for_reminders():
    """user_id списком для всех, у кого включены напоминания и заданы цели."""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT user_id FROM users WHERE (reminders_enabled IS NULL OR reminders_enabled = 1) AND calories_goal IS NOT NULL AND calories_goal > 0"
    )
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]


def log_reminder_sent(user_id):
    from datetime import datetime
    now = datetime.now()
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO reminder_log (user_id, sent_at, date) VALUES (?, ?, ?)",
        (user_id, now.isoformat(), now.date().isoformat())
    )
    conn.commit()
    conn.close()


def get_reminder_count_today(user_id):
    today = date.today().isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM reminder_log WHERE user_id = ? AND date = ?", (user_id, today))
    n = c.fetchone()[0]
    conn.close()
    return n


# --- Meals ---

def add_meal(user_id, name, calories, protein, fat, carbs):
    conn = get_conn()
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute(
        "INSERT INTO meals (user_id, name, calories, protein, fat, carbs, date) VALUES (?,?,?,?,?,?,?)",
        (user_id, name, calories, protein, fat, carbs, today)
    )
    conn.commit()
    conn.close()

def get_meals_today(user_id):
    conn = get_conn()
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute("SELECT id, name, calories, protein, fat, carbs FROM meals WHERE user_id=? AND date=?", (user_id, today))
    rows = c.fetchall()
    conn.close()
    return rows


def get_last_meal_today(user_id):
    """Последний приём пищи за сегодня: (created_at ISO str, name, calories) или None."""
    conn = get_conn()
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute(
        "SELECT created_at, name, calories FROM meals WHERE user_id=? AND date=? ORDER BY id DESC LIMIT 1",
        (user_id, today)
    )
    row = c.fetchone()
    conn.close()
    return row if row else None

def delete_last_meal(user_id):
    conn = get_conn()
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute("SELECT id FROM meals WHERE user_id=? AND date=? ORDER BY id DESC LIMIT 1", (user_id, today))
    row = c.fetchone()
    if row:
        c.execute("DELETE FROM meals WHERE id=?", (row[0],))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def get_daily_totals(user_id, target_date=None):
    conn = get_conn()
    c = conn.cursor()
    d = target_date or date.today().isoformat()
    c.execute(
        "SELECT SUM(calories), SUM(protein), SUM(fat), SUM(carbs) FROM meals WHERE user_id=? AND date=?",
        (user_id, d)
    )
    row = c.fetchone()
    conn.close()
    return {
        "calories": row[0] or 0,
        "protein": row[1] or 0,
        "fat": row[2] or 0,
        "carbs": row[3] or 0
    }

def get_meals_range(user_id, from_date, to_date):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT date, SUM(calories), SUM(protein), SUM(fat), SUM(carbs) FROM meals WHERE user_id=? AND date BETWEEN ? AND ? GROUP BY date ORDER BY date",
        (user_id, from_date, to_date)
    )
    rows = c.fetchall()
    conn.close()
    return rows

# --- Weight ---

def log_weight(user_id, weight):
    conn = get_conn()
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute("INSERT INTO weight_log (user_id, weight, date) VALUES (?,?,?)", (user_id, weight, today))
    # Update current weight in users table
    c.execute("UPDATE users SET weight=? WHERE user_id=?", (weight, user_id))
    conn.commit()
    conn.close()

def get_weight_history(user_id, limit=30):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT weight, date FROM weight_log WHERE user_id=? ORDER BY date DESC LIMIT ?", (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows

# --- Quick foods ---

def get_quick_foods(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, name, calories, protein, fat, carbs FROM quick_foods WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def add_quick_food(user_id, name, calories, protein, fat, carbs):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO quick_foods (user_id, name, calories, protein, fat, carbs) VALUES (?,?,?,?,?,?)",
        (user_id, name, calories, protein, fat, carbs)
    )
    conn.commit()
    conn.close()

def delete_quick_food(food_id, user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM quick_foods WHERE id=? AND user_id=?", (food_id, user_id))
    conn.commit()
    conn.close()

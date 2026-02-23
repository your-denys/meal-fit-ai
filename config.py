import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# PostgreSQL (Neon): добавляем sslmode=require, если в URL ещё нет
DATABASE_URL = os.getenv("DATABASE_URL") or ""
if DATABASE_URL and "sslmode=" not in DATABASE_URL:
    sep = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL = DATABASE_URL.rstrip("?&") + sep + "sslmode=require"

# Для webhook (Render и др.): базовый URL сервиса, например https://meal-fit-ai-xxx.onrender.com
WEBHOOK_BASE_URL = (os.getenv("WEBHOOK_BASE_URL") or "").rstrip("/")
# Секрет для заголовка X-Telegram-Bot-Api-Secret-Token (рекомендуется)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET") or None

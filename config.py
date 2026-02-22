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

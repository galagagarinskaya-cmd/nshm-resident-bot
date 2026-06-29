import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", 0))
TELEGRAM_ADMIN_IDS = list(map(int, os.getenv("TELEGRAM_ADMIN_IDS", "").split(","))) if os.getenv("TELEGRAM_ADMIN_IDS") else []

# Google Sheets
SHEETS_ID = "1kdWpaMIDDoQ87eJ-HoAzkldmVNbGEs9eROWhy3xwd00"
SHEETS_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")

# App config
DATABASE_PATH = "nshm_bot.db"
FLASK_PORT = int(os.getenv("FLASK_PORT", 5001))
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")

# Content
SELF_PROMO_DAY = "Thursday"  # День саморекламы
SELF_PROMO_THREAD = "Возможности друг для друга"
SURVEY_DELAY_DAYS = 3  # Дней до отправки опроса

# Rules blocks config
RULES_BLOCKS = ["ЧАСТЬ 1 — ОБЩЕНИЕ", "ЧАСТЬ 2 — РЕКЛАМА И ССЫЛКИ", "ЧАСТЬ 3 — ПОСЛЕДСТВИЯ", "ЧАСТЬ 4 — АПЕЛЛЯЦИЯ"]

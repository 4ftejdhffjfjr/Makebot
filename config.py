# config.py
import os
from dotenv import load_dotenv

# Папка, где лежит ЭТОТ config.py (и bot.py, и .env)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")

if not os.path.exists(ENV_PATH):
    raise SystemExit(f"❌ Файл .env не найден по пути: {ENV_PATH}\n"
                     f"Создай его рядом с bot.py в той же папке.")

load_dotenv(ENV_PATH)

BOT_TOKEN = os.getenv("7798461726:AAFpsAv9SevW_syTGfeRYnUdSrlzgVjEqeA")
ADMIN_ID = int(os.getenv("5029096746", "0"))
REQUIRED_CHANNEL = os.getenv("@Make_bots155", "")
ENCRYPTION_KEY = os.getenv("6YURra1GjvPtqFAuTzHSHNxRhtXw_bpo_qlzHxu5-Pg=
")

if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN не найден в .env")
if not ADMIN_ID:
    raise SystemExit("❌ ADMIN_ID не найден в .env")
if not ENCRYPTION_KEY:
    raise SystemExit("❌ ENCRYPTION_KEY не найден в .env")

# --- Прочие настройки ---
CONTACT_TEXT = "📞 Наши контакты:\nТелефон: +7 (995) 412-89-08\nАдмин: @Plot1335"
MAX_BOTS_PER_USER = 3
HOSTING_PRICE = 250
HOSTING_DAYS = 14

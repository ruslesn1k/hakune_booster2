# config.py

# === БОТ / БАЗА ===
BOT_TOKEN = "7521556241:AAHd4MC8DUySOub-SKEVFhuXYJnpQSztPJw"
DB_FILE = "bot.db"

# === РОЛИ/УВЕДОМЛЕНИЯ ===
admin_ids   = {1087260212, 987654321}
support_ids = {555666777, 111222333}
notify_ids  = admin_ids | support_ids
REVIEWS_CHAT_ID = -1002993838857

# (устаревшее, прямые переводы больше не используем — можно оставить пустым)
PAYMENT_LINK = ""

# === MARZBAN ===
MARZBAN_URL = "http://127.0.0.1:8000"
MARZBAN_USERNAME = "kenzu"
MARZBAN_PASSWORD = "Ruslesn1kof925"
# MARZBAN_API_TOKEN = ""  # если используешь токен вместо логина/пароля

# === ВНУТРЕННИЙ ВЕБ-СЕРВЕР ДЛЯ ВЕБХУКОВ/РЕДИРЕКТОВ (опционально) ===
RUN_INTERNAL_WEB = True      # True — поднимать FastAPI внутри бота
WEB_HOST = "0.0.0.0"
WEB_PORT = 8000

# Базовый публичный URL (домен, куда укажут вебхуки платёжных систем)
BASE_PUBLIC_URL = "https://pay.hakunebooster.ru"

# === ВКЛЮЧАЛКИ ПЛАТЁЖНЫХ СИСТЕМ ===
PAYPALYCH_ENABLED = False
YOOKASSA_ENABLED  = True
YOOMONEY_ENABLED  = False
STARS_ENABLED     = False   # Telegram Stars

# === PAYPALYCH ===
PAYPALYCH_SHOP_ID   = ""
PAYPALYCH_API_KEY   = ""
PAYPALYCH_SUCCESS_URL = f"{BASE_PUBLIC_URL}/pally/success"
PAYPALYCH_FAIL_URL    = f"{BASE_PUBLIC_URL}/pally/fail"
PAYPALYCH_RESULT_URL  = f"{BASE_PUBLIC_URL}/pally/result"

# === YOOKASSA ===
YOOKASSA_SHOP_ID    = "1157516"
YOOKASSA_SECRET_KEY = "test_T-tWe1yLN4rt5CZqwfShS6b2UsfIfR3urMVOhvSWsVc"
TELEGRAM_PROVIDER_TOKEN = "381764678:TEST:139677"
YOOKASSA_RETURN_URL = "https://t.me/haku_booster_bot"
CURRENCY = "RUB"
YOOKASSA_SEND_RECEIPT = True
YOOKASSA_TAX_SYSTEM_CODE = 1
YOOKASSA_VAT_CODE = 1
YOOKASSA_RECEIPT_PHONE = "79777707287"

# === YOOMONEY ===
YOOMONEY_WALLET_ID    = "4100116473289644"
YOOMONEY_ACCESS_TOKEN = "1BE42BA539FE1E811E166542B3295BFAD7CB1CF57D64A5003B84D729B6769817"
YOOMONEY_RETURN_URL   = f"{BASE_PUBLIC_URL}/yoomoney/return"
YOOMONEY_WEBHOOK_URL  = f"{BASE_PUBLIC_URL}/yoomoney/notify"

# === TELEGRAM STARS ===
STARS_PROVIDER_TOKEN = ""
BOT_USERNAME = ""

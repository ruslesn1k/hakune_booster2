# db.py
import aiosqlite
from config import DB_FILE
import datetime
import datetime as dt
import uuid
import json
from marzban_api import extend_user
import secrets, string
from typing import Optional, Tuple

# ---------- USERS ----------
CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id         INTEGER PRIMARY KEY,
    tg_username     TEXT,
    full_name       TEXT,
    phone           TEXT,
    nickname        TEXT,
    role            TEXT NOT NULL DEFAULT 'user',
    notify_enabled  INTEGER DEFAULT 1
);
"""

# ---------- TICKETS ----------
CREATE_TICKETS_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id              INTEGER,
    text                 TEXT,
    status               TEXT DEFAULT 'open',
    priority             INTEGER DEFAULT 1,
    created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
    closed_at            DATETIME,
    closed_by            INTEGER,
    last_admin_id        INTEGER,
    last_admin_name      TEXT,
    first_admin_reply_at DATETIME
);
"""

# ---------- TICKET MESSAGES ----------
CREATE_MESSAGES_SQL = """
CREATE TABLE IF NOT EXISTS ticket_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id  INTEGER,
    sender_id  INTEGER,
    text       TEXT,
    file_id    TEXT,
    media_type TEXT,
    sent_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

# ---------- TRIALS ----------
CREATE_TRIALS_SQL = """
CREATE TABLE IF NOT EXISTS trials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    used INTEGER NOT NULL DEFAULT 0,
    activated_at TIMESTAMP
);
"""

# ---------- SUBSCRIPTION PERIODS ----------
CREATE_PERIODS_SQL = """
CREATE TABLE IF NOT EXISTS subscription_periods (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    months INTEGER NOT NULL,
    price  REAL    NOT NULL
);
"""

# --------------- SUBSCRIPTIONS --------------
CREATE_SUBSCRIPTIONS_SQL = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    local_name TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, username)
);
"""

# ---------- PAYMENTS ----------
CREATE_PAYMENTS_SQL = """
CREATE TABLE IF NOT EXISTS payments (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER,
    period_id INTEGER,
    key_code  TEXT,
    amount    REAL,
    status    TEXT DEFAULT 'pending',
    photo_id  TEXT,
    extra     TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

# ---------- PROMO CODES ----------
CREATE_PROMO_SQL = """
CREATE TABLE IF NOT EXISTS promo_codes (
    code        TEXT PRIMARY KEY,
    months      INTEGER,
    activations INTEGER,
    used        INTEGER DEFAULT 0
);
"""

# ---------- LOCAL NAME ----------
CREATE_LOCAL_NAME_SQL = """
CREATE TABLE IF NOT EXISTS local_subs (
    user_id INTEGER,
    username TEXT,
    local_name TEXT,
    PRIMARY KEY (user_id, username)
);
"""

# ---------- KEYS ----------
CREATE_KEYS_SQL = """
CREATE TABLE IF NOT EXISTS keys (
    code        TEXT PRIMARY KEY,
    months      INTEGER NOT NULL,
    uses_left   INTEGER NOT NULL DEFAULT 1,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_by     INTEGER,
    used_at     TIMESTAMP
);
"""

# ---------- инициализация ----------
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(CREATE_USERS_SQL)
        await db.execute(CREATE_TICKETS_SQL)
        await db.execute(CREATE_MESSAGES_SQL)
        await db.execute(CREATE_PERIODS_SQL)
        await db.execute(CREATE_SUBSCRIPTIONS_SQL)
        await db.execute(CREATE_PAYMENTS_SQL)
        await db.execute(CREATE_PROMO_SQL)
        await db.execute(CREATE_TRIALS_SQL)
        await db.execute(CREATE_LOCAL_NAME_SQL)
        await db.execute(CREATE_KEYS_SQL)
        await db.commit()

# ========================================
# ---------- USERS ----------
async def save_user(user_id, tg_username, full_name, phone, nickname, role):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR REPLACE INTO users(user_id, tg_username, full_name, phone, nickname, role) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, tg_username, full_name, phone, nickname, role)
        )
        await db.commit()

async def get_user_role(user_id: int) -> str:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT role FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else "user"

# ========================================
# ---------- PERIODS ----------
async def add_subscription_period(months: int, price: float):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO subscription_periods(months, price) VALUES (?, ?)", (months, price))
        await db.commit()

async def get_subscription_periods():
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT id, months, price FROM subscription_periods ORDER BY months")
        return await cur.fetchall()

async def get_subscription_period_by_id(period_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT id, months, price FROM subscription_periods WHERE id = ?", (period_id,))
        return await cur.fetchone()

# ========================================
# ---------- PAYMENTS ----------

async def add_payment(*args, **kwargs) -> int:
    """
    Универсальная вставка в таблицу:
    схема таблицы: (id, user_id, period_id, key_code, amount, status, photo_id, extra, created_at)
    - метод оплаты НЕ хранится в отдельной колонке (method нет).
    - статус по умолчанию 'pending'.
    Поддерживает вызовы как позиционно, так и именованно (с игнором method).
    """
    # нормализуем аргументы
    # возможные входы:
    # 1) add_payment(user_id, period_id, key_code, amount, photo_id, extra_json)
    # 2) add_payment(user_id=..., amount=..., status='pending', photo_id=None, extra=..., period_id=None, key_code=None, method='yookassa')
    if args and not kwargs:
        # вариант №1 — позиционные
        user_id, period_id, key_code, amount, photo_id, extra_json = args
        status = "pending"
    else:
        user_id   = kwargs.get("user_id")
        period_id = kwargs.get("period_id")
        key_code  = kwargs.get("key_code")
        amount    = kwargs.get("amount")
        status    = kwargs.get("status", "pending")
        photo_id  = kwargs.get("photo_id")
        # ignore possibly passed 'method'
        extra_val = kwargs.get("extra")
        # сериализуем dict в JSON, если пришёл dict
        if isinstance(extra_val, (dict, list)):
            extra_json = json.dumps(extra_val, ensure_ascii=False)
        else:
            extra_json = extra_val

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            INSERT INTO payments (user_id, period_id, key_code, amount, status, photo_id, extra)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, period_id, key_code, amount, status, photo_id, extra_json)
        )
        await db.commit()
        cur = await db.execute("SELECT last_insert_rowid()")
        row = await cur.fetchone()
        return row[0]

async def get_payment_by_id(payment_id: int):
    """
    Возвращает кортеж совместимый с вызывающим кодом:
    (id, user_id, amount, status, purpose, extra, created_at)
    Колонки 'method' и 'purpose' в схеме нет — вернём purpose=None.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute(
            "SELECT id, user_id, amount, status, extra, created_at FROM payments WHERE id = ?",
            (payment_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        pid, user_id, amount, status, extra, created_at = row
        purpose = None
        return (pid, user_id, amount, status, purpose, extra, created_at)

# ========================================
# ---------- KEYS ----------
def _gen_key(length: int = 16) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

async def generate_key(months: int, uses_left: int = 1, length: int = 16) -> str:
    while True:
        code = _gen_key(length)
        row = await get_key(code)
        if not row:
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute("INSERT INTO keys(code, months, uses_left) VALUES(?,?,?)", (code, months, uses_left))
                await db.commit()
            return code

async def get_key(code: str):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT code, months, uses_left, created_at, used_by, used_at FROM keys WHERE code=?", (code,))
        return await cur.fetchone()

async def consume_key(code: str, user_id: int):
    row = await get_key(code)
    if not row:
        return None
    code, months, uses_left, *_ = row
    if uses_left <= 0:
        return None
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE keys SET uses_left=uses_left-1, used_by=?, used_at=CURRENT_TIMESTAMP WHERE code=?", (user_id, code))
        await db.commit()
    return months

# ========================================
# ---------- LOCAL SUBS (личные имена) ----------
async def set_local_name(user_id: int, username: str, local_name: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR REPLACE INTO local_subs(user_id, username, local_name) VALUES (?, ?, ?)",
            (user_id, username, local_name)
        )
        await db.commit()

async def get_local_name(user_id: int, username: str) -> str | None:
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute(
            "SELECT local_name FROM local_subs WHERE user_id=? AND username=?",
            (user_id, username)
        )
        row = await cur.fetchone()
        return row[0] if row else None

async def delete_local_name(user_id: int, username: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "DELETE FROM local_subs WHERE user_id=? AND username=?",
            (user_id, username)
        )
        await db.commit()

# ---- Алиасы для совместимости со старым кодом ----
async def get_periods():
    # вернуть список [(id, months, price), ...]
    return await get_subscription_periods()

async def get_period_by_id(period_id: int):
    # вернуть (id, months, price)
    return await get_subscription_period_by_id(period_id)

async def get_subscription_periods():
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute(
            "SELECT id, months, price FROM subscription_periods ORDER BY months"
        )
        return await cur.fetchall()

async def get_subscription_period_by_id(period_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute(
            "SELECT id, months, price FROM subscription_periods WHERE id = ?",
            (period_id,),
        )
        return await cur.fetchone()

# ---------- SUBSCRIPTION PERIODS (delete) ----------
async def delete_subscription_period(period_id: int) -> None:
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM subscription_periods WHERE id = ?", (period_id,))
        await db.commit()

# Алиас для старого кода (если где-то вызывается)
async def delete_period(period_id: int) -> None:
    await delete_subscription_period(period_id)
    
# ---------- SUBSCRIPTIONS ----------
# 1) список подписок пользователя (username, local_name)
async def get_user_subscriptions(user_id: int):
    async with aiosqlite.connect(DB_FILE) as _db:
        cur = await _db.execute(
            "SELECT username, local_name FROM subscriptions WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        rows = await cur.fetchall()
        return [(r[0], r[1]) for r in rows]

# 2) локальное имя
async def set_local_name(user_id: int, username: str, local_name: str):
    async with aiosqlite.connect(DB_FILE) as _db:
        # если записи нет — создадим, иначе обновим
        await _db.execute(
            """
            INSERT INTO subscriptions(user_id, username, local_name, created_at)
            VALUES(?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, username) DO UPDATE SET local_name=excluded.local_name
            """,
            (user_id, username, local_name),
        )
        await _db.commit()

# 3) периоды подписок (из таблицы subscription_periods)
async def get_subscription_periods():
    async with aiosqlite.connect(DB_FILE) as _db:
        cur = await _db.execute("SELECT id, months, price FROM subscription_periods ORDER BY months")
        return await cur.fetchall()  # [(id, months, price)]

async def get_subscription_period_by_id(pid: int):
    async with aiosqlite.connect(DB_FILE) as _db:
        cur = await _db.execute("SELECT id, months, price FROM subscription_periods WHERE id = ?", (pid,))
        return await cur.fetchone()
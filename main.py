import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re

from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import config as cfg
BOT_TOKEN = getattr(cfg, "BOT_TOKEN", None) or getattr(cfg, "TOKEN", None)
if not BOT_TOKEN:
    raise RuntimeError("В config.py должен быть BOT_TOKEN (или TOKEN)")

LOG_DIR = Path(getattr(cfg, "LOG_DIR", "logs"))
_admin_ids_raw = getattr(cfg, "admin_ids", [])
ADMIN_IDS = {int(x) for x in _admin_ids_raw}

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(fmt, datefmt))
    root.addHandler(ch)
    fh = RotatingFileHandler(LOG_DIR / "bot.log", maxBytes=5*1024*1024, backupCount=5, encoding="utf-8")
    fh.setFormatter(logging.Formatter(fmt, datefmt))
    root.addHandler(fh)

setup_logging()
logger = logging.getLogger("bot.main")

import db
import keyboards as kb
from reg import RegStates
from cabinet import cabinet_router
from tickets import ticket_router
from trial import trial_router
from reviews import review_router
from handlers.admin_stats import admin_stats_router
from handlers.admin_products import admin_products_router
from marzban_api import check_connection
from switch_kb import switch_router
from keyboards import main_menu
from shop import shop_router
from payments import routers as payment_routers

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# include routers
dp.include_router(admin_stats_router)
dp.include_router(admin_products_router)
dp.include_router(cabinet_router)
dp.include_router(ticket_router)
dp.include_router(trial_router)
dp.include_router(review_router)
dp.include_router(switch_router)
dp.include_router(shop_router)
for r in payment_routers:
    dp.include_router(r)

@dp.message(CommandStart())
async def on_start(message: Message):
    role = "admin" if is_admin(message.from_user.id) else "client"
    await message.answer(
        "👋 Приветствую в Hakune Booster!\nНажмите кнопку ниже, чтобы начать регистрацию:",
        reply_markup=kb.register_ikb if hasattr(kb, "register_ikb") else main_menu(role)
    )

@dp.callback_query(F.data == "register")
async def start_registration(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if hasattr(kb, "share_contact_kb"):
        await callback.message.answer("📞 Поделитесь контактом:", reply_markup=kb.share_contact_kb)
    else:
        await callback.message.answer("📞 Отправьте свой контакт.")
    await state.set_state(RegStates.waiting_contact)

@dp.message(RegStates.waiting_contact, F.contact)
async def receive_contact(message: Message, state: FSMContext):
    contact = message.contact
    await state.update_data(
        user_id=contact.user_id,
        full_name=(contact.first_name or "") + (f" {contact.last_name}" if contact.last_name else ""),
        phone=contact.phone_number,
        tg_username=message.from_user.username or ""
    )
    await message.answer("✅ Контакт сохранён!\nТеперь введите ник (латиница/цифры/нижнее подчёркивание).")
    await state.set_state(RegStates.waiting_nickname)

NICK_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")

@dp.message(RegStates.waiting_nickname, F.text)
async def receive_nickname(message: Message, state: FSMContext):
    nickname = (message.text or "").strip()
    if not NICK_RE.match(nickname):
        await message.answer("❗️ Ник должен быть латиницей/цифрами/нижним подчёркиванием (3–32 символа).")
        return
    data = await state.get_data()
    full_name = data.get("full_name", "")
    phone = data.get("phone", "")
    tg_username = data.get("tg_username", message.from_user.username or "")
    try:
        await db.save_user(
            user_id=message.from_user.id,
            tg_username=tg_username,
            full_name=full_name,
            phone=phone,
            nickname=nickname,
            role="admin" if is_admin(message.from_user.id) else "user",
        )
    except Exception as e:
        logger.exception("Ошибка сохранения пользователя: %s", e)
        await message.answer("❌ Не удалось сохранить данные. Попробуйте ещё раз.")
        return
    await state.clear()
    role = "admin" if is_admin(message.from_user.id) else "client"
    await message.answer("✅ Регистрация завершена!", reply_markup=main_menu(role))

@dp.message(Command("mstatus"))
async def marzban_status(message: Message):
    if not is_admin(message.from_user.id):
        return
    ok = await check_connection()
    await message.answer("✅ Подключено к Marzban" if ok else "❌ Нет подключения к Marzban")

async def on_startup():
    # инициализация БД и миграция keys
    if hasattr(db, "init_keys_schema"):
        await db.init_keys_schema()
    if hasattr(db, "init_db"):
        await db.init_db()
    logger.info("Инициализация БД завершена.")
    ok = await check_connection()
    logger.info("Статус Marzban: %s", "OK" if ok else "NO CONNECTION")

async def main():
    await on_startup()
    logger.info("Запускаю polling…")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())

from aiogram import Router, types
from aiogram.filters import Command
from keyboards import main_menu
import config as cfg

switch_router = Router()

ADMIN_IDS = {int(x) for x in getattr(cfg, "admin_ids", [])}

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@switch_router.message(Command("switch_admin"))
async def switch_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    await message.answer("✅ Режим администратора.", reply_markup=main_menu("admin"))

@switch_router.message(Command("switch_user"))
async def switch_user(message: types.Message):
    await message.answer("✅ Режим клиента.", reply_markup=main_menu("client"))

@switch_router.message(Command("switch_back"))
async def switch_back(message: types.Message):
    role = "admin" if is_admin(message.from_user.id) else "client"
    await message.answer("🔄 Главное меню восстановлено.", reply_markup=main_menu(role))

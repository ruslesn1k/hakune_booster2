from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from config import PAYPALYCH_ENABLED

pally_router = Router(name="paypalych") if PAYPALYCH_ENABLED else None

if pally_router:
    @pally_router.callback_query(F.data == "pm_pally")
    async def choose_pally(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        amount = data.get("amount")
        name = data.get("product_name","Оплата VPN")
        desc = data.get("product_desc","Оплата услуг VPN")
        # тут обычно создаётся счёт через API PayPalych, передаём name/desc
        await callback.message.answer(
            f"🧾 <b>{name}</b>\n{desc}\n\n"
            f"Сумма к оплате: <b>{amount:.2f} ₽</b>\n"
            "PayPalych будет подключён здесь. (демо)"
        )
        await callback.answer()

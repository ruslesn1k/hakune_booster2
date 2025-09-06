from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from config import STARS_ENABLED

stars_router = Router(name="stars") if STARS_ENABLED else None

if stars_router:
    @stars_router.callback_query(F.data == "pm_stars")
    async def choose_stars(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        amount = data.get("amount")
        name = data.get("product_name","Оплата VPN")
        desc = data.get("product_desc","Оплата услуг VPN")
        await callback.message.answer(
            f"🧾 <b>{name}</b>\n{desc}\n\n"
            f"Сумма к оплате: <b>{amount:.2f} ₽</b>\n"
            "Оплата звёздами Telegram здесь. (демо)"
        )
        await callback.answer()

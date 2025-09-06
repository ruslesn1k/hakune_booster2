# trial.py
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

import db
from marzban_api import create_paid_user, get_user_subscription_link

trial_router = Router(name="trial")

TRIAL_DAYS = 7

@trial_router.callback_query(F.data == "get_trial")
async def get_trial_handler(callback: CallbackQuery):
    user_id = callback.from_user.id

    # Проверим, использовал ли юзер уже триал
    already = await db.has_trial(user_id)
    if already:
        await callback.answer("❌ Вы уже использовали пробный период.", show_alert=True)
        return

    # Создаём триал-подписку в панели
    username = f"trial_{user_id}"
    try:
        created = await create_paid_user(username=username, months=0, trial_days=TRIAL_DAYS)
    except Exception as e:
        logging.exception("Ошибка при создании триала: %s", e)
        await callback.answer("Ошибка при создании пробной подписки.", show_alert=True)
        return

    if not created:
        await callback.answer("❌ Не удалось создать подписку.", show_alert=True)
        return

    # Получаем ссылку
    try:
        sub_link = await get_user_subscription_link(username=username)
    except Exception as e:
        logging.exception("Ошибка при получении trial-ссылки: %s", e)
        sub_link = None

    # Запишем в базу
    await db.mark_trial_used(user_id)

    kb = None
    if sub_link:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Ваша подписка", url=sub_link)]
        ])

    await callback.message.answer(
        f"🎁 Вам доступен бесплатный пробный период {TRIAL_DAYS} дней!\n\n"
        f"🔗 Ссылка: {sub_link if sub_link else 'не удалось получить'}",
        reply_markup=kb
    )
    await callback.answer()

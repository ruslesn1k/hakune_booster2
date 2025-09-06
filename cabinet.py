# cabinet.py
from __future__ import annotations

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

import db
from marzban_api import get_user_subscription_link
from config import YOOKASSA_ENABLED

cabinet_router = Router(name="cabinet")

# ---------- FSM ----------
class RenameStates(StatesGroup):
    waiting_new_name = State()
    # держим в state: username

class RenewStates(StatesGroup):
    choosing_period = State()
    # держим в state: username
    # после выбора периода положим: amount, months, ptype="renew", renew_username=username
    # это заберёт payments/yookassa.py (pm_yookassa)

# ---------- КНОПКИ/КЛАВЫ ----------
def _sub_row_kb(username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Ссылка", callback_data=f"cab_link:{username}")],
            [InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"cab_ren:{username}")],
            [InlineKeyboardButton(text="🔄 Продлить", callback_data=f"cab_renew:{username}")],
        ]
    )

def _periods_kb(periods) -> InlineKeyboardMarkup:
    # periods: list[(id, months, price)]
    rows = []
    for pid, months, price in periods:
        rows.append([InlineKeyboardButton(text=f"{months} мес — {price:.2f} ₽", callback_data=f"cab_rp:{pid}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="cab_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def _payments_kb() -> InlineKeyboardMarkup:
    rows = []
    if YOOKASSA_ENABLED:
        rows.append([InlineKeyboardButton(text="💳 Оплатить ЮKassa", callback_data="pm_yookassa")])
    rows.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="cab_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ---------- ОТКРЫТИЕ КАБИНЕТА ----------
async def _send_cabinet(message: Message):
    subs = await db.get_user_subscriptions(message.from_user.id)
    if not subs:
        await message.answer(
            "У вас пока нет подписок.\n"
            "Оформите покупку в разделе «🛍 Купить подписку»."
        )
        return
    # subs: list[(username, local_name | None)]
    for username, local_name in subs:
        name = local_name or username
        await message.answer(
            f"📡 <b>{name}</b>\n<code>{username}</code>",
            reply_markup=_sub_row_kb(username)
        )

@cabinet_router.message(F.text == "👤 Личный кабинет")
async def open_cabinet_btn(message: Message):
    await _send_cabinet(message)

@cabinet_router.callback_query(F.data == "cab_back")
async def cab_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await _send_cabinet(callback.message)

# ---------- ССЫЛКА ----------
@cabinet_router.callback_query(F.data.startswith("cab_link:"))
async def cab_link(callback: CallbackQuery):
    username = callback.data.split(":", 1)[1]
    link = await get_user_subscription_link(username)
    if not link:
        await callback.answer("Не удалось получить ссылку.", show_alert=True)
        return
    await callback.message.answer(
        f"🔗 Ссылка для <b>{username}</b>:\n{link}"
    )
    await callback.answer()

# ---------- ПЕРЕИМЕНОВАНИЕ ----------
@cabinet_router.callback_query(F.data.startswith("cab_ren:"))
async def cab_rename(callback: CallbackQuery, state: FSMContext):
    username = callback.data.split(":", 1)[1]
    await state.update_data(username=username)
    await state.set_state(RenameStates.waiting_new_name)
    await callback.message.answer("Введите новое название для подписки:")
    await callback.answer()

@cabinet_router.message(RenameStates.waiting_new_name)
async def cab_set_new_name(message: Message, state: FSMContext):
    data = await state.get_data()
    username = data.get("username")
    new_name = (message.text or "").strip()
    if not new_name:
        await message.answer("Название не должно быть пустым. Введите заново:")
        return
    await db.set_local_name(message.from_user.id, username, new_name)
    await message.answer(f"✅ Название для <code>{username}</code> сохранено как <b>{new_name}</b>.")
    await state.clear()

# ---------- ПРОДЛЕНИЕ ----------
@cabinet_router.callback_query(F.data.startswith("cab_renew:"))
async def renew_start(callback: CallbackQuery, state: FSMContext):
    username = callback.data.split(":", 1)[1]
    await state.update_data(username=username)
    periods = await db.get_subscription_periods()
    if not periods:
        await callback.answer("Тарифы (периоды) не настроены.", show_alert=True)
        return
    await state.set_state(RenewStates.choosing_period)
    await callback.message.answer(
        f"Выберите срок продления для <b>{username}</b>:",
        reply_markup=_periods_kb(periods)
    )
    await callback.answer()

@cabinet_router.callback_query(RenewStates.choosing_period, F.data.startswith("cab_rp:"))
async def renew_pick_period(callback: CallbackQuery, state: FSMContext):
    try:
        period_id = int(callback.data.split(":", 1)[1])
    except Exception:
        await callback.answer("Некорректный период.", show_alert=True)
        return

    row = await db.get_subscription_period_by_id(period_id)
    if not row:
        await callback.answer("Период не найден.", show_alert=True)
        return

    pid, months, price = row
    data = await state.get_data()
    username = data.get("username")

    # подготовим данные для платежного модуля (pm_yookassa)
    await state.update_data(
        amount=float(price),
        months=int(months),
        ptype="renew",
        renew_username=username,
        product_name=f"Продление VPN — {months} мес.",
        product_desc=f"Продление подписки <{username}> на {months} месяцев.",
    )

    await callback.message.answer(
        f"Продление <b>{username}</b> на <b>{months}</b> мес.\n"
        f"К оплате: <b>{price:.2f} ₽</b>",
        reply_markup=_payments_kb()
    )
    await callback.answer()

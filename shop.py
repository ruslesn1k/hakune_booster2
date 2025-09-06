from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import db
from payments.payment_states import PaymentStates
from marzban_api import create_paid_user, extend_user, get_user_subscription_link

shop_router = Router(name="shop")

# ====== FSM для ввода ключа ======
class KeyStates(StatesGroup):
    waiting_key = State()

def _methods_kb(flags: dict[str,bool]) -> InlineKeyboardMarkup:
    rows = []
    if flags.get("PAYPALYCH_ENABLED"):
        rows.append([InlineKeyboardButton(text="PayPalych", callback_data="pm_pally")])
    if flags.get("YOOKASSA_ENABLED"):
        rows.append([InlineKeyboardButton(text="YooKassa", callback_data="pm_yookassa")])
    if flags.get("YOOMONEY_ENABLED"):
        rows.append([InlineKeyboardButton(text="ЮMoney", callback_data="pm_yoomoney")])
    if flags.get("STARS_ENABLED"):
        rows.append([InlineKeyboardButton(text="Telegram Stars", callback_data="pm_stars")])
    if not rows:
        rows.append([InlineKeyboardButton(text="Нет доступных методов оплаты", callback_data="no_methods")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def _periods_kb(periods, prefix: str) -> InlineKeyboardMarkup:
    rows = []
    for pid, months, price in periods:
        rows.append([InlineKeyboardButton(text=f"{months} мес · {price:.2f} ₽", callback_data=f"{prefix}{pid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def build_description(ptype: str, months: int, username: str | None = None) -> tuple[str,str]:
    if ptype == "new":
        name = f"VPN подписка — {months} мес."
        desc = ("Безлимитный VPN доступ на выбранный срок. "
                "Подключение до 5 устройств, стабильные сервера, поддержка 24/7. "
                "Активация по ссылке в боте.")
    elif ptype == "renew":
        name = f"Продление VPN — {months} мес."
        desc = (f"Продление подписки {username} на {months} месяцев. "
                "Действует с момента оплаты, остаток переносится.")
    elif ptype == "key":
        name = f"VPN ключ — {months} мес."
        desc = ("Активационный ключ для VPN на указанный срок. "
                "Можно подарить: отправьте ключ другу, он активирует его в боте.")
    else:
        name = "Оплата VPN"
        desc = "Оплата услуг VPN."
    return name, desc

# ========= Покупка новой подписки =========
@shop_router.message(F.text.in_({"💳 Купить подписку", "/buy"}))
async def buy_entry(message: Message, state: FSMContext):
    periods = await db.get_periods()
    if not periods:
        await message.answer("Периоды подписки пока не добавлены.")
        return
    await state.update_data(ptype="new")
    await message.answer("Выберите период:", reply_markup=_periods_kb(periods, prefix="period_"))

@shop_router.callback_query(F.data.startswith("period_"))
async def period_chosen(callback: CallbackQuery, state: FSMContext):
    period_id = int(callback.data.split("_", 1)[1])
    row = await db.get_subscription_period_by_id(period_id)
    if not row:
        await callback.answer("Период не найден", show_alert=True); return
    _, months, price = row
    await state.update_data(period_id=period_id, months=months, amount=price)
    # собрать описание
    name, desc = build_description("new", months)
    await state.update_data(product_name=name, product_desc=desc)
    from config import PAYPALYCH_ENABLED, YOOKASSA_ENABLED, YOOMONEY_ENABLED, STARS_ENABLED
    flags = {
        "PAYPALYCH_ENABLED": bool(PAYPALYCH_ENABLED),
        "YOOKASSA_ENABLED": bool(YOOKASSA_ENABLED),
        "YOOMONEY_ENABLED": bool(YOOMONEY_ENABLED),
        "STARS_ENABLED": bool(STARS_ENABLED),
    }
    await callback.message.answer(
        f"<b>{name}</b>\n{desc}\n\nК оплате: {price:.2f} ₽\nВыберите способ оплаты:",
        reply_markup=_methods_kb(flags)
    )
    await state.set_state(PaymentStates.choosing_method)
    await callback.answer()

# ========= Продление =========
@shop_router.message(F.text.in_({"🔄 Продлить подписку", "/renew"}))
async def renew_entry(message: Message, state: FSMContext):
    subs = await db.get_user_subscriptions(message.from_user.id)
    if not subs:
        await message.answer("У вас пока нет подписок для продления."); return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"renew_pick_{name}")] for name in subs
    ])
    await message.answer("Выберите подписку для продления:", reply_markup=kb)

@shop_router.callback_query(F.data.startswith("renew_pick_"))
async def renew_pick(callback: CallbackQuery, state: FSMContext):
    username = callback.data.replace("renew_pick_","",1)
    periods = await db.get_periods()
    if not periods:
        await callback.message.answer("Периоды подписки пока не добавлены."); await callback.answer(); return
    await state.update_data(ptype="renew", renew_username=username)
    await callback.message.answer(f"Продление <b>{username}</b>. Выберите период:", reply_markup=_periods_kb(periods, prefix="renew_period_"))
    await callback.answer()

@shop_router.callback_query(F.data.startswith("renew_period_"))
async def renew_period(callback: CallbackQuery, state: FSMContext):
    period_id = int(callback.data.split("_", 2)[2])
    row = await db.get_period_by_id(period_id)
    if not row:
        await callback.answer("Период не найден", show_alert=True); return
    _, months, price = row
    await state.update_data(period_id=period_id, months=months, amount=price)
    username = (await state.get_data()).get("renew_username")
    name, desc = build_description("renew", months, username)
    await state.update_data(product_name=name, product_desc=desc)
    from config import PAYPALYCH_ENABLED, YOOKASSA_ENABLED, YOOMONEY_ENABLED, STARS_ENABLED
    flags = {
        "PAYPALYCH_ENABLED": bool(PAYPALYCH_ENABLED),
        "YOOKASSA_ENABLED": bool(YOOKASSA_ENABLED),
        "YOOMONEY_ENABLED": bool(YOOMONEY_ENABLED),
        "STARS_ENABLED": bool(STARS_ENABLED),
    }
    await callback.message.answer(
        f"<b>{name}</b>\n{desc}\n\nК оплате: {price:.2f} ₽\nВыберите способ оплаты:",
        reply_markup=_methods_kb(flags)
    )
    await state.set_state(PaymentStates.choosing_method)
    await callback.answer()

# ========= Купить ключ =========
@shop_router.message(F.text.in_({"🔑 Купить ключ", "/buy_key"}))
async def buy_key_entry(message: Message, state: FSMContext):
    periods = await db.get_periods()
    if not periods:
        await message.answer("Периоды ключей пока не добавлены."); return
    await state.update_data(ptype="key")
    await message.answer("Выберите срок действия ключа:", reply_markup=_periods_kb(periods, prefix="key_period_"))

@shop_router.callback_query(F.data.startswith("key_period_"))
async def key_period(callback: CallbackQuery, state: FSMContext):
    period_id = int(callback.data.split("_", 2)[2])
    row = await db.get_period_by_id(period_id)
    if not row:
        await callback.answer("Период не найден", show_alert=True); return
    _, months, price = row
    await state.update_data(period_id=period_id, months=months, amount=price)
    name, desc = build_description("key", months)
    await state.update_data(product_name=name, product_desc=desc)
    from config import PAYPALYCH_ENABLED, YOOKASSA_ENABLED, YOOMONEY_ENABLED, STARS_ENABLED
    flags = {
        "PAYPALYCH_ENABLED": bool(PAYPALYCH_ENABLED),
        "YOOKASSA_ENABLED": bool(YOOKASSA_ENABLED),
        "YOOMONEY_ENABLED": bool(YOOMONEY_ENABLED),
        "STARS_ENABLED": bool(STARS_ENABLED),
    }
    await callback.message.answer(
        f"<b>{name}</b>\n{desc}\n\nК оплате: {price:.2f} ₽\nВыберите способ оплаты:",
        reply_markup=_methods_kb(flags)
    )
    await state.set_state(PaymentStates.choosing_method)
    await callback.answer()

# ====== Ввести ключ ======
@shop_router.message(F.text.in_({"🔑 Ввести ключ", "/enter_key"}))
async def enter_key_start(message: Message, state: FSMContext):
    await message.answer("🔑 Отправьте ключ активации (латиница/цифры, без пробелов).")
    await state.set_state(KeyStates.waiting_key)

@shop_router.message(KeyStates.waiting_key, F.text)
async def process_key(message: Message, state: FSMContext):
    code = (message.text or "").strip().upper()
    row = await db.get_key(code)
    if not row:
        await message.answer("❌ Ключ не найден."); return
    _code, months, uses_left, *_ = row
    if uses_left <= 0:
        await message.answer("❌ Ключ уже использован."); return
    months_to_add = await db.consume_key(code, message.from_user.id)
    if not months_to_add:
        await message.answer("❌ Не удалось активировать ключ. Попробуйте ещё раз."); return
    subs = await db.get_user_subscriptions(message.from_user.id)
    if subs:
        username = subs[0]
        ok = await extend_user(username, months_to_add)
        link = await get_user_subscription_link(username) or ""
        txt = f"✅ Ключ применён. Подписка <b>{username}</b> продлена на {months_to_add} мес."
        if link: txt += f"\n🔗 Ссылка: {link}"
        await message.answer(txt)
    else:
        username = f"key_{message.from_user.id}_{code}"
        ok = await create_paid_user(username, months_to_add)
        if not ok:
            await message.answer("⚠ Ключ списан, но создать подписку не удалось. Напишите в поддержку."); await state.clear(); return
        await db.set_local_name(message.from_user.id, username, username)
        link = await get_user_subscription_link(username) or ""
        txt = f"✅ Ключ применён. Создана подписка <b>{username}</b> на {months_to_add} мес."
        if link: txt += f"\n🔗 Ссылка: {link}"
        await message.answer(txt)
    await state.clear()

@shop_router.callback_query(F.data == "no_methods")
async def no_methods(callback: CallbackQuery):
    await callback.answer("Нет включённых платёжных систем. Обратитесь в поддержку.", show_alert=True)

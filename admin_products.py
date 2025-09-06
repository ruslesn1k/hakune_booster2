from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import db

admin_products_router = Router()


# ==========================
# FSM
# ==========================
class AddSubscription(StatesGroup):
    months = State()
    price = State()


class AddPromo(StatesGroup):
    months = State()
    activations = State()


# ==========================
# Клавиатуры
# ==========================
def products_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Подписки", callback_data="admin_products:subs")],
        [InlineKeyboardButton(text="🔑 Ключи", callback_data="admin_products:keys")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_products:back")],
    ])


def subscription_list_kb(periods):
    buttons = []
    for pid, months, price in periods:
        buttons.append([
            InlineKeyboardButton(
                text=f"{months} мес. — {price}₽",
                callback_data=f"admin_products:del_sub:{pid}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="➕ Добавить", callback_data="admin_products:add_sub")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_products:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def promo_list_kb(codes):
    buttons = []
    for code, months, uses_left, created_at, used_by, used_at in codes:
        buttons.append([
            InlineKeyboardButton(
                text=f"{code} ({months} мес., осталось {uses_left})",
                callback_data=f"admin_products:del_key:{code}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="➕ Добавить", callback_data="admin_products:add_key")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_products:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==========================
# Handlers
# ==========================
@admin_products_router.message(F.text == "🛒 Товары")
async def products_menu(msg: Message):
    await msg.answer("Выберите категорию:", reply_markup=products_menu_kb())


# Подписки
@admin_products_router.callback_query(F.data == "admin_products:subs")
async def show_subscriptions(cb: CallbackQuery):
    subs = await db.get_subscription_periods()
    await cb.message.edit_text("📅 Подписки:", reply_markup=subscription_list_kb(subs))


@admin_products_router.callback_query(F.data.startswith("admin_products:del_sub:"))
async def delete_subscription(cb: CallbackQuery):
    period_id = int(cb.data.split(":")[-1])
    await db.delete_subscription_period(period_id)
    subs = await db.get_subscription_periods()
    await cb.message.edit_text("📅 Подписки:", reply_markup=subscription_list_kb(subs))


@admin_products_router.callback_query(F.data == "admin_products:add_sub")
async def start_add_subscription(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("Введите срок подписки (в месяцах):")
    await state.set_state(AddSubscription.months)


@admin_products_router.message(AddSubscription.months)
async def process_sub_months(msg: Message, state: FSMContext):
    await state.update_data(months=int(msg.text))
    await msg.answer("Введите цену (в ₽):")
    await state.set_state(AddSubscription.price)


@admin_products_router.message(AddSubscription.price)
async def process_sub_price(msg: Message, state: FSMContext):
    data = await state.get_data()
    months = data["months"]
    price = int(msg.text)
    await db.add_subscription_period(months, price)
    await state.clear()
    subs = await db.get_subscription_periods()
    await msg.answer("📅 Подписки:", reply_markup=subscription_list_kb(subs))


# Ключи
@admin_products_router.callback_query(F.data == "admin_products:keys")
async def show_keys(cb: CallbackQuery):
    codes = await db.get_all_keys()
    await cb.message.edit_text("🔑 Ключи:", reply_markup=promo_list_kb(codes))


@admin_products_router.callback_query(F.data.startswith("admin_products:del_key:"))
async def delete_key(cb: CallbackQuery):
    code = cb.data.split(":")[-1]
    await db.delete_key(code)
    codes = await db.get_all_keys()
    await cb.message.edit_text("🔑 Ключи:", reply_markup=promo_list_kb(codes))


@admin_products_router.callback_query(F.data == "admin_products:add_key")
async def start_add_key(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("Введите срок действия ключа (в месяцах):")
    await state.set_state(AddPromo.months)


@admin_products_router.message(AddPromo.months)
async def process_key_months(msg: Message, state: FSMContext):
    await state.update_data(months=int(msg.text))
    await msg.answer("Введите количество активаций:")
    await state.set_state(AddPromo.activations)


@admin_products_router.message(AddPromo.activations)
async def process_key_activations(msg: Message, state: FSMContext):
    data = await state.get_data()
    months = data["months"]
    activations = int(msg.text)
    code = await db.generate_key(months, activations)
    await state.clear()
    codes = await db.get_all_keys()
    await msg.answer(f"✅ Ключ {code} создан", reply_markup=promo_list_kb(codes))


# Назад
@admin_products_router.callback_query(F.data == "admin_products:back")
async def back_to_products(cb: CallbackQuery):
    await cb.message.edit_text("Выберите категорию:", reply_markup=products_menu_kb())

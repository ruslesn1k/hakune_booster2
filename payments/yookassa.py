# payments/yookassa.py
from __future__ import annotations

import uuid
import json
import datetime
import html

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
)

from yookassa import Configuration, Payment

import db
from config import (
    YOOKASSA_ENABLED,
    YOOKASSA_SHOP_ID,
    YOOKASSA_SECRET_KEY,
    YOOKASSA_RETURN_URL,  # например https://t.me/<your_bot>
)

from marzban_api import (
    create_paid_user,            # create_paid_user(username: str, months: int) -> bool
    extend_user,                 # extend_user(username: str, months: int) -> bool | None
    get_user_subscription_link,  # get_user_subscription_link(username: str) -> str | None
)


# Роутер ЮKassa (подключи его в main.py: dp.include_router(yookassa_router))
yookassa_router = Router(name="yookassa")

# Если в конфиге отключено — хендлеры просто не будут использоваться
if YOOKASSA_ENABLED:
    Configuration.account_id = str(YOOKASSA_SHOP_ID or "").strip()
    Configuration.secret_key = str(YOOKASSA_SECRET_KEY or "").strip()


# ==========================
#        УТИЛИТЫ
# ==========================

async def _merge_payment_extra(payment_id: int, patch: dict) -> None:
    """
    Аккуратно вольём patch в JSON payments.extra (не затирая существующее).
    """
    import aiosqlite
    from config import DB_FILE

    async with aiosqlite.connect(DB_FILE) as _db:
        cur = await _db.execute("SELECT extra FROM payments WHERE id = ?", (payment_id,))
        row = await cur.fetchone()
        base = {}
        if row and row[0]:
            try:
                base = json.loads(row[0])
            except Exception:
                base = {}
        base.update(patch)
        await _db.execute(
            "UPDATE payments SET extra = ? WHERE id = ?",
            (json.dumps(base, ensure_ascii=False), payment_id),
        )
        await _db.commit()


def _unpack_payment_row(row: tuple):
    """
    Совместимая распаковка платежа из БД:
    - Новая схема: (id, user_id, amount, method, status, photo_id, extra, created_at) -> len == 8
    - Старая схема: (id, user_id, amount, status, purpose, extra, created_at) -> len == 7
    Возвращаем унифицированный набор:
      pid, user_id, amount, method, status, photo_id, purpose, extra_json, created_at
    """
    if row is None:
        return None

    if len(row) == 8:
        # Новая схема
        pid, user_id, amount, method, status, photo_id, extra_json, created_at = row
        purpose = None
        return pid, user_id, amount, method, status, photo_id, purpose, extra_json, created_at

    if len(row) == 7:
        # Старая схема
        pid, user_id, amount, status, purpose, extra_json, created_at = row
        method = None
        photo_id = None
        return pid, user_id, amount, method, status, photo_id, purpose, extra_json, created_at

    # неизвестный формат
    return None


async def _on_payment_approved(message: Message, payment_id: int) -> None:
    """
    Позвать, когда платёж в ЮKassa = succeeded:
    - new: создать подписку, показать ссылку
    - renew: продлить username на months
    - key: сгенерировать активационный ключ
    """
    row = await db.get_payment_by_id(payment_id)
    up = _unpack_payment_row(row)
    if not up:
        await message.answer("❌ Платёж не найден или неподдерживаемый формат.")
        return

    pid, user_id, amount, method, status, photo_id, purpose, extra_json, created_at = up

    # ptype/прочее берём из extra (source of truth)
    meta = {}
    try:
        meta = json.loads(extra_json) if extra_json else {}
    except Exception:
        meta = {}

    ptype = (purpose or meta.get("ptype") or "new").strip().lower()    # new | renew | key
    months = int(meta.get("months", 1))
    username = meta.get("username")  # для renew
    product_name = meta.get("product_name") or "Оплата подписки"

    if ptype == "renew":
        if not username:
            await message.answer("⚠ Оплата прошла, но username для продления не указан. Напишите в поддержку.")
            return
        ok = await extend_user(username, months)
        link = await get_user_subscription_link(username) or ""
        if ok is False:
            await message.answer("⚠ Не удалось продлить подписку. Напишите в поддержку.")
            return

        text = f"✅ Платёж подтверждён.\nПодписка <b>{username}</b> продлена на {months} мес."
        if link:
            text += f"\n🔗 Ссылка: {link}"
        await message.answer(text)
        return

    if ptype == "key":
        code = await db.generate_key(months=months, uses_left=1)
        await message.answer(
            "✅ Оплата подтверждена!\n"
            f"🔑 Ваш активационный ключ: <code>{code}</code>\n\n"
            "Перейдите в раздел «🔑 Ввести ключ» и отправьте этот код."
        )
        return

        # new — создаём подписку
    new_username = f"paid_{user_id}_{payment_id}"

    # Совместимый вызов для разных версий marzban_api.create_paid_user:
    created_ok = False
    try:
        # новая сигнатура: (username, months)
        created_ok = await create_paid_user(new_username, months)
    except TypeError:
        try:
            # вариант с именованными аргументами
            created_ok = await create_paid_user(username=new_username, months=months)
        except TypeError:
            try:
                # очень старая сигнатура: (user_id, sub_number, months)
                created_ok = await create_paid_user(user_id, payment_id, months)
            except Exception:
                created_ok = False

    if not created_ok:
        await message.answer("⚠ Оплата прошла, но создать подписку не удалось. Напишите в поддержку.")
        return

    # Сохраняем локальное имя (чтобы показывалось в «Мои подписки»)
    try:
        if hasattr(db, "set_local_name"):
            await db.set_local_name(user_id, new_username, new_username)
    except Exception:
        pass

    async def _on_payment_approved(message, payment_id: int, new_username: str, months: int):
        link = await get_user_subscription_link(new_username) or ""
        safe_username = html.escape(new_username)

        text = (
            "✅ Оплата подтверждена!\n\n"
            f"📡 Подписка создана: <code>{safe_username}</code>\n"
            f"⏳ Срок: {months} мес."
        )

        if link:
            text += f"\n🔗 Ссылка: {html.escape(link)}"

        await message.answer(text)

# ==========================
#        ХЕНДЛЕРЫ
# ==========================

@yookassa_router.callback_query(F.data == "pm_yookassa")
async def yk_create_payment(callback: CallbackQuery, state: FSMContext):
    """
    Создание платежа в YooKassa и выдача кнопки «Оплатить».
    Ожидаем, что до этого в state были записаны:
      - amount: float
      - months: int
      - ptype: "new" | "renew" | "key"
      - renew_username: Optional[str]
      - product_name: Optional[str]
      - product_desc: Optional[str]
    """
    if not YOOKASSA_ENABLED or not (YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY):
        await callback.message.answer("ЮKassa не настроена. Обратитесь в поддержку.")
        await callback.answer()
        return

    data = await state.get_data()
    amount = float(data.get("amount", 0.0))
    months = int(data.get("months", 1))
    ptype = (data.get("ptype") or "new").strip().lower()
    renew_username = data.get("renew_username")

    product_name = data.get("product_name") or f"Подписка VPN — {months} мес."
    product_desc = data.get("product_desc") or (
        "Высокая скорость, стабильные сервера и круглосуточная поддержка.\n"
        "Безлимитный трафик, доступ к локациям, подключение в один клик."
    )

    # 1) создаём запись платежа в нашей БД (pending)
    extra = {
        "ptype": ptype,
        "months": months,
        "username": renew_username,
        "product_name": product_name,
        "product_desc": product_desc,
        "via": "yookassa",
        "started_at": datetime.datetime.utcnow().isoformat(),
    }
    extra_json = json.dumps(extra, ensure_ascii=False)

    # Совместимость с разными версиями db.add_payment
    try:
        payment_id = await db.add_payment(
            user_id=callback.from_user.id,
            amount=amount,
            method="yookassa",
            status="pending",
            photo_id=None,
            extra=extra_json,
        )
    except TypeError:
        # старая сигнатура: (user_id, period_id, key_code, amount, photo_id, extra)
        payment_id = await db.add_payment(
            callback.from_user.id,
            None,
            None,
            amount,
            None,
            extra_json,
        )

    # 2) создаём платёж в YooKassa
    description = f"{product_name} (tg:{callback.from_user.id}, pid:{payment_id})"
    yo_payment = Payment.create({
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": YOOKASSA_RETURN_URL or "https://t.me",
        },
        "capture": True,
        "description": description,
        # "metadata": {"tg_id": str(callback.from_user.id), "local_pid": str(payment_id)},
    }, uuid.uuid4())

    confirmation_url = yo_payment.confirmation.confirmation_url
    yk_payment_id = yo_payment.id

    # 3) сохраним id платежа YooKassa в extra
    await _merge_payment_extra(payment_id, {"yk_payment_id": yk_payment_id})

    # 4) выдаём пользователю кнопки
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить (ЮKassa)", url=confirmation_url)],
            [InlineKeyboardButton(text="🔁 Проверить оплату", callback_data=f"pm_yk_check_{payment_id}")],
        ]
    )
    await callback.message.answer(
        f"🧾 <b>{product_name}</b>\n{product_desc}\n\n"
        f"Сумма к оплате: <b>{amount:.2f} ₽</b>\n\n"
        "Нажмите «Оплатить», затем вернитесь в бот и нажмите «Проверить оплату».",
        reply_markup=kb
    )
    await callback.answer()


@yookassa_router.callback_query(F.data.startswith("pm_yk_check_"))
async def yk_check_payment(callback: CallbackQuery):
    """
    Проверка статуса платежа в YooKassa и, при успехе, выдача услуги.
    """
    try:
        payment_id = int(callback.data.rsplit("_", 1)[-1])
    except Exception:
        await callback.answer("Некорректный платёж.", show_alert=True)
        return

    row = await db.get_payment_by_id(payment_id)
    up = _unpack_payment_row(row)
    if not up:
        await callback.answer("Платёж не найден.", show_alert=True)
        return

    pid, user_id, amount, method, status, photo_id, purpose, extra_json, created_at = up

    if status == "approved":
        await callback.answer("Оплата уже подтверждена ✅", show_alert=True)
        return
    if status == "rejected":
        await callback.answer("Платёж отклонён.", show_alert=True)
        return

    # достаём из extra id платежа в YooKassa
    meta = {}
    try:
        meta = json.loads(extra_json) if extra_json else {}
    except Exception:
        meta = {}

    yk_payment_id = meta.get("yk_payment_id")
    if not yk_payment_id:
        await callback.answer("Нет идентификатора платежа YooKassa. Напишите в поддержку.", show_alert=True)
        return

    yo_payment = Payment.find_one(yk_payment_id)
    yo_status = getattr(yo_payment, "status", None)

    if yo_status == "succeeded":
        # помечаем платеж как подтверждённый
        try:
            await db.update_payment_status(payment_id, "approved")
        except AttributeError:
            # если вдруг не добавил хелпер — сделаем прямым апдейтом
            import aiosqlite
            from config import DB_FILE
            async with aiosqlite.connect(DB_FILE) as _db:
                await _db.execute("UPDATE payments SET status = ? WHERE id = ?", ("approved", payment_id))
                await _db.commit()

        # выдаём услугу
        await _on_payment_approved(callback.message, payment_id)
        await callback.answer("Оплата подтверждена ✅")
        return

    if yo_status in ("canceled", "expired"):
        try:
            await db.update_payment_status(payment_id, "rejected")
        except AttributeError:
            import aiosqlite
            from config import DB_FILE
            async with aiosqlite.connect(DB_FILE) as _db:
                await _db.execute("UPDATE payments SET status = ? WHERE id = ?", ("rejected", payment_id))
                await _db.commit()

        await callback.answer("Платёж отменён/истёк.", show_alert=True)
        return

    # waiting_for_capture | pending и т.п.
    await callback.answer("Платёж пока не завершён. Попробуйте позже.", show_alert=True)

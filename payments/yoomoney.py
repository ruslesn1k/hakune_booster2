# payments/yoomoney.py
import aiosqlite
from config import DB_FILE
import json
import aiohttp
import asyncio
import datetime
import urllib.parse
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
import json as _json

import db
from config import (
    YOOMONEY_ENABLED,
    YOOMONEY_WALLET_ID,
    YOOMONEY_ACCESS_TOKEN,
    YOOMONEY_RETURN_URL,
)
from marzban_api import create_paid_user, extend_user, get_user_subscription_link

# Включаем роутер только если платёжка активна
yoomoney_router = Router(name="yoomoney") if YOOMONEY_ENABLED else None

API_HOST = "https://yoomoney.ru"
API_OP_HISTORY = f"{API_HOST}/api/operation-history"

def _fmt_amount(amount: float) -> str:
    # ЮMoney ждёт точку как разделитель
    return f"{amount:.2f}"

def build_quickpay_url(
    receiver: str,
    amount: float,
    label: str,
    name: str,
    desc: str,
    success_url: str,
    payment_type: str | None = None,  # "AC" (карта) | "PC" (ЮMoney) | None (выбор на форме)
) -> str:
    """
    Документация Quickpay:
    https://yoomoney.ru/docs/payment-buttons/using-api/forms
    """
    params = {
        "receiver": receiver,
        "quickpay-form": "shop",        # shop|donate — для товара лучше shop
        "sum": _fmt_amount(amount),
        "label": label,                 # наша метка для поиска платежа в API
        "targets": name[:128],          # заголовок платежа
        "comment": desc[:512],          # описание
        "successURL": success_url,
    }
    if payment_type:
        params["paymentType"] = payment_type
    qs = urllib.parse.urlencode(params, safe=":/")
    return f"{API_HOST}/quickpay/confirm.xml?{qs}"


async def _yoomoney_find_paid(label: str, min_amount: float) -> bool:
    """
    Проверяем в истории операций по метке label наличие успешного платежа на сумму >= min_amount.
    https://yoomoney.ru/docs/wallet/user-account/operations-history
    """
    headers = {"Authorization": f"Bearer {YOOMONEY_ACCESS_TOKEN}"}
    params = {"label": label, "records": 30}
    async with aiohttp.ClientSession() as sess:
        async with sess.get(API_OP_HISTORY, headers=headers, params=params) as resp:
            if resp.status != 200:
                text = await resp.text()
                # Можно залогировать text
                return False
            data = await resp.json()
    # Ответ содержит массив operations
    # operation example keys: operation_id, status ('success'), amount, label, datetime, ...
    for op in data.get("operations", []):
        if op.get("status") == "success" and op.get("label") == label:
            try:
                amt = float(op.get("amount", 0))
            except Exception:
                amt = 0.0
            if amt + 1e-6 >= float(min_amount):
                return True
    return False


async def _on_payment_approved(message: Message, payment_id: int):
    """
    Действия после подтверждения оплаты:
    - new   -> создать подписку
    - renew -> продлить username
    - key   -> сгенерировать ключ и отправить
    """
    row = await db.get_payment_by_id(payment_id)
    if not row:
        await message.answer("❌ Платёж не найден.")
        return
    _pid, user_id, amount, status, purpose, extra_json, created_at = row
    extra = {}
    try:
        extra = json.loads(extra_json or "{}")
    except Exception:
        pass

    months = int(extra.get("months", 1))
    username = extra.get("username")
    ptype = purpose or extra.get("ptype") or "new"

    if ptype == "renew":
        if not username:
            await message.answer("❌ Не указан username для продления. Свяжитесь с поддержкой.")
            return
        ok = await extend_user(username, months)
        link = await get_user_subscription_link(username) or ""
        txt = f"✅ Оплата получена. Подписка <b>{username}</b> продлена на {months} мес."
        if link:
            txt += f"\n🔗 Ссылка: {link}"
        await message.answer(txt)
        return

    if ptype == "key":
        # Генерируем ключ на months и отправляем
        code = await db.generate_key(months=months, uses_left=1)
        await message.answer(
            "✅ Оплата получена. Ваш активационный ключ:\n"
            f"🔑 <code>{code}</code>\n\n"
            "В боте нажмите «🔑 Ввести ключ» и отправьте этот код."
        )
        return

    # По умолчанию — новая подписка
    new_username = f"paid_{user_id}_{payment_id}"
    ok = await create_paid_user(new_username, months)
    if not ok:
        await message.answer("⚠ Оплата прошла, но создать подписку не удалось. Напишите в поддержку.")
        return

    # Запишем локально
    if hasattr(db, "upsert_subscription"):
        await db.upsert_subscription(user_id, new_username, local_name=new_username)
    link = await get_user_subscription_link(new_username) or ""
    txt = (
        f"✅ Оплата получена!\n"
        f"📡 Подписка <b>{new_username}</b> создана на {months} мес.\n"
    )
    if link:
        txt += f"\n🔗 Ссылка: {link}"
    await message.answer(txt)


if yoomoney_router:

    @yoomoney_router.callback_query(F.data == "pm_yoomoney")
    async def choose_yoomoney(callback: CallbackQuery, state: FSMContext):
        """
        Создаём платёж, выдаём ссылку QuickPay и кнопку «Проверить оплату».
        Все параметры (ptype, months, username и т.п.) складываем в payments.extra
        """
        data = await state.get_data()
        amount = float(data.get("amount", 0))
        months = int(data.get("months", 1))
        ptype = data.get("ptype", "new")            # new|renew|key
        username = data.get("renew_username")       # только для renew
        name = data.get("product_name", "Оплата VPN")
        desc = data.get("product_desc", "Оплата услуг VPN")

        if not YOOMONEY_WALLET_ID or not YOOMONEY_ACCESS_TOKEN:
            await callback.message.answer("ЮMoney не настроен. Обратитесь в поддержку.")
            await callback.answer()
            return

        # Создаём платёж в своей БД (совместимость с разными сигнатурами add_payment)
        extra = {
            "ptype": ptype,
            "months": months,
            "username": username,
            "product_name": name,
            "product_desc": desc,
        }
        extra_json = _json.dumps(extra, ensure_ascii=False)

        try:
            # вариант, где add_payment принимает именованные параметры и поле photo_id
            payment_id = await db.add_payment(
                user_id=callback.from_user.id,
                amount=amount,
                purpose=ptype,
                photo_id=None,  # для авто-платежей фото нет
                extra=extra_json,  # <-- ПЕРЕДАЁМ СТРОКУ, НЕ dict
            )
        except TypeError:
            try:
                # старый стиль с позиционными параметрами: (user_id, amount, purpose, photo_id, extra)
                payment_id = await db.add_payment(
                    callback.from_user.id,
                    amount,
                    ptype,
                    None,  # photo_id
                    extra_json,  # <-- тоже строка JSON
                )
            except Exception as e:
                await callback.message.answer(f"Ошибка создания платежа: {e}")
                await callback.answer()
                return

        # Присваиваем метку и сохраняем её в payments.extra (добавим к уже сохранённому JSON)
        label = f"YM-{payment_id}-{callback.from_user.id}"

        # если есть утилита обновления extra — используем её
        if hasattr(db, "update_payment_extra"):
            try:
                await db.update_payment_extra(payment_id, {"label": label, **extra})
            except Exception:
                # прямой апдейт
                async with aiosqlite.connect(DB_FILE) as _db:
                    merged = {**extra, "label": label}
                    await _db.execute(
                        "UPDATE payments SET extra = ? WHERE id = ?",
                        (_json.dumps(merged, ensure_ascii=False), payment_id),
                    )
                    await _db.commit()
        else:
            # прямой апдейт
            async with aiosqlite.connect(DB_FILE) as _db:
                merged = {**extra, "label": label}
                await _db.execute(
                    "UPDATE payments SET extra = ? WHERE id = ?",
                    (_json.dumps(merged, ensure_ascii=False), payment_id),
                )
                await _db.commit()

        pay_url = build_quickpay_url(
            receiver=YOOMONEY_WALLET_ID,
            amount=amount,
            label=label,
            name=name,
            desc=desc,
            success_url=YOOMONEY_RETURN_URL or "https://yoomoney.ru",
            payment_type=None,  # пусть пользователь сам выберет (карта/ЮMoney)
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить (ЮMoney)", url=pay_url)],
                [InlineKeyboardButton(text="🔁 Проверить оплату", callback_data=f"pm_yoomoney_check_{payment_id}")],
            ]
        )

        await callback.message.answer(
            f"🧾 <b>{name}</b>\n{desc}\n\n"
            f"Сумма к оплате: <b>{amount:.2f} ₽</b>\n\n"
            "Нажмите «Оплатить», совершите перевод и затем «Проверить оплату».",
            reply_markup=kb
        )
        await callback.answer()

    # Нужен импорт aiosqlite внутрь файла (используем выше для апдейта extra)
    import aiosqlite

    @yoomoney_router.callback_query(F.data.startswith("pm_yoomoney_check_"))
    async def check_payment(callback: CallbackQuery):
        payment_id = int(callback.data.rsplit("_", 1)[-1])
        row = await db.get_payment_by_id(payment_id)
        if not row:
            await callback.answer("Платёж не найден.", show_alert=True)
            return
        _pid, user_id, amount, status, purpose, extra_json, created_at = row
        if status == "approved":
            await callback.answer("Уже оплачено ✅", show_alert=True)
            return
        if status == "rejected":
            await callback.answer("Платёж отклонён.", show_alert=True)
            return

        try:
            extra = json.loads(extra_json or "{}")
        except Exception:
            extra = {}
        label = extra.get("label")
        if not label:
            await callback.answer("Нет метки платежа (label). Обратитесь в поддержку.", show_alert=True)
            return

        ok = await _yoomoney_find_paid(label, float(amount))
        if not ok:
            await callback.answer("Платёж пока не найден. Попробуйте позже.", show_alert=True)
            return

        # Подтверждаем в БД и выполняем действие
        await db.update_payment_status(payment_id, "approved")
        await _on_payment_approved(callback.message, payment_id)
        await callback.answer("Оплата подтверждена ✅")

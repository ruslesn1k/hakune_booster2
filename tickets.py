# tickets.py
import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
import db
from config import notify_ids, admin_ids, support_ids
import keyboards as kb

logger = logging.getLogger(__name__)
ticket_router = Router()

class TicketStates(StatesGroup):
    entering_text = State()
    answering = State()

class AddMessageStates(StatesGroup):
    typing = State()

# ----------------- ПОЛЬЗОВАТЕЛЬ -----------------
@ticket_router.message(F.text == "🛠 Тех.Поддержка")
async def user_open_support_menu(message: Message):
    await message.answer("Выберите действие:", reply_markup=kb.support_submenu)

@ticket_router.message(F.text == "📨 Отправить тикет")
async def user_start_ticket(message: Message, state: FSMContext):
    await message.answer("📝 Опишите вашу проблему (можно приложить фото/файл):")
    await state.set_state(TicketStates.entering_text)

@ticket_router.message(TicketStates.entering_text)
async def user_send_ticket(message: Message, state: FSMContext, bot: Bot):
    text = message.text or message.caption or ""
    file_id, media_type = None, None
    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        media_type = "document"

    ticket_id = await db.create_ticket(message.from_user.id, text, priority=1)
    await db.add_message(ticket_id, message.from_user.id, text, file_id, media_type)
    logger.info("Пользователь %d создал тикет #%d", message.from_user.id, ticket_id)

    for uid in notify_ids:
        try:
            await bot.send_message(uid, f"⚠️ Новый тикет #{ticket_id} от {message.from_user.id}")
            if file_id:
                if media_type == "photo":
                    await bot.send_photo(uid, file_id, caption=text[:1024])
                else:
                    await bot.send_document(uid, file_id, caption=text[:1024])
        except Exception:
            pass
    await message.answer("✅ Тикет отправлен! Ожидайте ответа.", reply_markup=kb.main_menu("user"))
    await state.clear()

@ticket_router.message(F.text == "📋 Мои тикеты")
async def user_list_tickets(message: Message):
    rows = await db.get_tickets(user_id=message.from_user.id)
    if not rows:
        await message.answer("У вас ещё нет тикетов.", reply_markup=kb.support_submenu)
        return
    for tid, _, text, status, _, created, _ in rows:
        if status == "open":
            await message.answer(
                f"📋 Тикет #{tid} (🔴 открыт)\n\n{text}\nСоздан: {created}",
                reply_markup=kb.user_add_message_button(tid)
            )
        else:
            await message.answer(
                f"📋 Тикет #{tid} (🟢 закрыт)\n\n{text}\nСоздан: {created}",
                reply_markup=kb.view_full_dialog_button(tid)
            )

@ticket_router.message(F.text == "⬅️ Назад")
async def user_back_to_main(message: Message):
    role = await db.get_user_role(message.from_user.id)
    await message.answer("Возвращаемся в главное меню", reply_markup=kb.main_menu(role))

# ----------------- АДМИН / САППОРТ -----------------
@ticket_router.message(F.text == "📂 Открытые тикеты")
async def list_open_tickets(message: Message):
    rows = await db.get_tickets(only_open=True)
    if not rows:
        await message.answer("Нет открытых тикетов.", reply_markup=kb.admin_back)
        return
    for tid, uid, text, _, priority, created, last_admin_name in rows:
        note = f"\n🟡 В работе – {last_admin_name}" if last_admin_name else ""
        prio = "🔴" if priority == 3 else "🟡" if priority == 2 else "🟢"
        await message.answer(
            f"{prio} Тикет #{tid} от {uid}{note}\n\n{text}",
            reply_markup=kb.admin_full_actions(tid)
        )

@ticket_router.message(F.text == "📜 История тикетов")
async def history_tickets(message: Message):
    rows = await db.get_tickets()
    if not rows:
        await message.answer("История пуста.", reply_markup=kb.admin_back)
        return
    for tid, uid, text, status, _, created, last_admin_name in rows:
        emoji = "🟢" if status == "closed" else "🔴"
        worked = f"\n👤 Работал: {last_admin_name}" if last_admin_name else ""
        await message.answer(f"{emoji} Тикет #{tid} от {uid}{worked}\n\n{text}")

@ticket_router.message(F.text == "⚡ Шаблоны")
async def show_quick_answers(message: Message):
    await message.answer("Введите /add_quick <имя> <текст>  или  /quick <имя>")

@ticket_router.message(F.text.startswith("/add_quick "))
async def add_quick(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3:
        await message.answer("Формат: /add_quick <имя> <текст>")
        return
    name, text = parts[1], parts[2]
    await db.add_quick_answer(name, text)
    await message.answer("✅ Шаблон добавлен")

@ticket_router.message(F.text.startswith("/quick "))
async def use_quick(message: Message, state: FSMContext):
    name = message.text.split(maxsplit=1)[1]
    text = await db.get_quick_answer(name)
    if not text:
        await message.answer("Шаблон не найден.")
        return
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    if ticket_id:
        await message.answer(text)
    else:
        await message.answer("Сначала выберите тикет для ответа.")

@ticket_router.message(F.text == "🔔 Уведомления ON/OFF")
async def toggle_notifications(message: Message):
    on = await db.toggle_notify(message.from_user.id)
    await message.answer("Уведомления " + ("включены" if on else "выключены"))

@ticket_router.message(F.text == "⬅️ Назад")
async def admin_back_to_main(message: Message):
    role = await db.get_user_role(message.from_user.id)
    await message.answer("Возвращаемся в главное меню", reply_markup=kb.main_menu(role))

# ----------------- CALLBACK ОБРАБОТКА -----------------
@ticket_router.callback_query(F.data.startswith("answer_"))
async def admin_answer_prompt(callback: CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split("_")[1])
    await state.update_data(ticket_id=ticket_id)
    await callback.message.answer("💬 Отправьте ваш ответ:")
    await state.set_state(TicketStates.answering)
    await callback.answer()

@ticket_router.message(TicketStates.answering)
async def admin_send_answer(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    ticket_id = data["ticket_id"]
    text = message.text or message.caption or ""
    file_id, media_type = None, None
    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        media_type = "document"
    await db.add_message(ticket_id, message.from_user.id, text, file_id, media_type)
    logger.info("Админ %d ответил в тикете #%d", message.from_user.id, ticket_id)

    info = await db.get_ticket_info(ticket_id)
    user_id = info[1]
    try:
        await bot.send_message(user_id, f"💬 Ответ на тикет #{ticket_id}:")
        if file_id:
            if media_type == "photo":
                await bot.send_photo(user_id, file_id, caption=text[:1024])
            else:
                await bot.send_document(user_id, file_id, caption=text[:1024])
        else:
            await bot.send_message(user_id, text)
    except Exception:
        pass
    await message.answer("✅ Ответ отправлен пользователю.")
    await state.clear()

@ticket_router.callback_query(F.data.startswith("close_"))
async def close_ticket_callback(callback: CallbackQuery, bot: Bot):
    ticket_id = int(callback.data.split("_")[1])
    await db.close_ticket(ticket_id, callback.from_user.id)
    info = await db.get_ticket_info(ticket_id)
    user_id = info[1]
    closer_name = info[6] or str(callback.from_user.id)
    try:
        await bot.send_message(user_id, f"🔒 Ваш тикет #{ticket_id} закрыт.\nСпасибо за обращение!")
    except Exception:
        pass
    logger.info("Тикет #%d закрыт админом %d", ticket_id, callback.from_user.id)
    await callback.message.edit_text(f"🔒 Тикет #{ticket_id} закрыт пользователем {closer_name}.", reply_markup=None)
    await callback.answer()

# --- пользователь добавляет сообщение ---
@ticket_router.callback_query(F.data.startswith("addmsg_"))
async def user_add_msg_prompt(callback: CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split("_")[1])
    await state.update_data(ticket_id=ticket_id)
    await callback.message.answer("🖊️ Отправьте ещё одно сообщение или файл:")
    await state.set_state(AddMessageStates.typing)
    await callback.answer()

@ticket_router.message(AddMessageStates.typing)
async def user_send_more(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    ticket_id = data["ticket_id"]
    text = message.text or message.caption or ""
    file_id, media_type = None, None
    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        media_type = "document"
    await db.add_message(ticket_id, message.from_user.id, text, file_id, media_type)
    logger.info("Пользователь %d добавил сообщение в #%d", message.from_user.id, ticket_id)
    for uid in notify_ids:
        try:
            await bot.send_message(uid, f"💬 Пользователь {message.from_user.id} добавил сообщение в тикет #{ticket_id}")
        except Exception:
            pass
    await message.answer("✅ Сообщение добавлено.", reply_markup=kb.user_add_message_button(ticket_id))
    await state.clear()

# --- пользователь закрывает свой тикет ---
@ticket_router.callback_query(F.data.startswith("userclose_"))
async def user_close_own(callback: CallbackQuery, bot: Bot):
    ticket_id = int(callback.data.split("_")[1])
    info = await db.get_ticket_info(ticket_id)
    if not info or info[3] != "open":
        await callback.answer("Тикет уже закрыт или не существует.", show_alert=True)
        return
    await db.close_ticket(ticket_id, callback.from_user.id)
    logger.info("Пользователь %d закрыл тикет #%d", callback.from_user.id, ticket_id)
    await callback.message.edit_text("🔒 Вы закрыли тикет.", reply_markup=None)
    await callback.answer()

# --- универсальный просмотр диалога ---
@ticket_router.callback_query(F.data.startswith("fulldialog_"))
async def show_full_dialog(callback: CallbackQuery, bot: Bot):
    ticket_id = int(callback.data.split("_", 1)[1])
    messages = await db.get_ticket_messages(ticket_id)
    if not messages:
        await callback.answer("Диалог пуст.", show_alert=True)
        return
    for sender_id, text, file_id, media_type, sent_at in messages:
        prefix = "👤 Вы:" if sender_id == callback.from_user.id else "💬 Поддержка:"
        if media_type == "photo":
            await bot.send_photo(callback.from_user.id, file_id, caption=f"{prefix} {text or ''}")
        elif media_type == "document":
            await bot.send_document(callback.from_user.id, file_id, caption=f"{prefix} {text or ''}")
        else:
            await bot.send_message(callback.from_user.id, f"{prefix} {text}")
    await callback.answer()
# keyboards.py
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup
)

# ---------- Reply ----------
share_contact_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
    resize_keyboard=True
)

register_ikb = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="✅ Зарегистрироваться", callback_data="register")]]
)

support_submenu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📨 Отправить тикет"), KeyboardButton(text="📋 Мои тикеты")],
        [KeyboardButton(text="⬅️ Назад")]
    ],
    resize_keyboard=True
)

admin_back = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="⬅️ Назад")]],
    resize_keyboard=True
)

admin_actions_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💳 Платежи на проверку"), KeyboardButton(text="📂 Открытые тикеты")],
        [KeyboardButton(text="📜 История тикетов"), KeyboardButton(text="⚡ Шаблоны")],
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="🛒 Товары")],
        [KeyboardButton(text="🔔 Уведомления ON/OFF")]
    ],
    resize_keyboard=True
)

support_admin_back = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="⬅️ Назад")]],
    resize_keyboard=True
)

def main_menu(role: str) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)
    if role == "admin":
        kb.keyboard = admin_actions_kb.keyboard
    elif role == "support":
        kb.keyboard = [
            [KeyboardButton(text="📂 Открытые тикеты"), KeyboardButton(text="📜 История тикетов")],
            [KeyboardButton(text="⚡ Шаблоны"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🔔 Уведомления ON/OFF")],
            [KeyboardButton(text="⬅️ Назад")]
        ]
    else:
        kb.keyboard = [
            [KeyboardButton(text="🎁 Пробная подписка"), KeyboardButton(text="🔑 Ввести ключ")],
            [KeyboardButton(text="💳 Купить подписку"), KeyboardButton(text="🔑 Купить ключ")],
            [KeyboardButton(text="🛠 Тех.Поддержка"), KeyboardButton(text="⭐ Отзывы")],
            [KeyboardButton(text="👤 Личный кабинет")] 
        ]
    return kb

# Меню отзывов
reviews_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📖 Все отзывы")],
        [KeyboardButton(text="📝 Оставить отзыв")],
        [KeyboardButton(text="⬅️ Назад")],
    ],
    resize_keyboard=True
)

# ---------- Inline ----------
def ticket_actions(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Ответить", callback_data=f"answer_{ticket_id}")],
            [InlineKeyboardButton(text="🔒 Закрыть", callback_data=f"close_{ticket_id}")],
            [InlineKeyboardButton(text="↩️ Выйти", callback_data=f"quit_{ticket_id}")]
        ]
    )

def view_full_dialog_button(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Весь диалог", callback_data=f"fulldialog_{ticket_id}")]
        ]
    )

def user_add_message_button(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Добавить сообщение", callback_data=f"addmsg_{ticket_id}")],
            [InlineKeyboardButton(text="📄 Весь диалог", callback_data=f"fulldialog_{ticket_id}")],
            [InlineKeyboardButton(text="🔒 Закрыть тикет", callback_data=f"userclose_{ticket_id}")]
        ]
    )

def admin_full_actions(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Весь диалог", callback_data=f"fulldialog_{ticket_id}")],
            [InlineKeyboardButton(text="💬 Ответить", callback_data=f"answer_{ticket_id}")],
            [InlineKeyboardButton(text="🔒 Закрыть", callback_data=f"close_{ticket_id}")],
            [InlineKeyboardButton(text="↩️ Выйти", callback_data=f"quit_{ticket_id}")]
        ]
    )

# --- оплата ---
def choose_period_kb(periods) -> InlineKeyboardMarkup:
    builder = []
    for pid, months, price in periods:
        builder.append([InlineKeyboardButton(text=f"{months} мес. – {price}₽", callback_data=f"period_{pid}")])
    return InlineKeyboardMarkup(inline_keyboard=builder)

def choose_payment_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Реквизиты", callback_data="pay_requisites")],
            [InlineKeyboardButton(text="📷 QR-код", callback_data="pay_qr")],
            [InlineKeyboardButton(text="🔗 Ссылка (сбербанк)", callback_data="pay_link")]
        ]
    )

def submit_payment_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Я оплатил", callback_data="submit_payment")]]
    )

def pending_payments_kb(payments) -> InlineKeyboardMarkup:
    builder = []
    for pid, uid, amount, _, _, _ in payments:
        builder.append([InlineKeyboardButton(text=f"#{pid} {amount}₽ от {uid}", callback_data=f"paycheck_{pid}")])
    return InlineKeyboardMarkup(inline_keyboard=builder)

def approve_reject_kb(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_{payment_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{payment_id}")]
        ]
    )
from aiogram import Router, F
from aiogram.types import Message
import db

admin_stats_router = Router()


@admin_stats_router.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    # --- Тикеты ---
    rows = await db.stats("2024-01-01")  # или DATE('now','-7 days')
    if rows:
        tickets_lines = [
            f"{row[0] or 'Без имени'}: {row[1]} шт, среднее {row[2] or 0:.1f} мин."
            for row in rows
        ]
        tickets_text = "📈 Статистика закрытых тикетов:\n" + "\n".join(tickets_lines)
    else:
        tickets_text = "📈 Нет закрытых тикетов за период."

    # --- Общая статистика ---
    users = await db.get_users_count()
    subs = await db.get_subscription_periods()
    keys = await db.get_promo_codes()
    earnings = await db.get_total_earnings()

    common_text = (
        "📊 Общая статистика\n"
        f"👥 Пользователей: {users}\n"
        f"📅 Подписок (всего видов): {len(subs)}\n"
        f"🔑 Ключей (всего создано): {len(keys)}\n"
        f"💰 Заработок: {earnings} ₽"
    )

    # --- Итог ---
    await message.answer(tickets_text + "\n\n" + common_text)

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove

from keyboards import reviews_menu, main_menu
from config import REVIEWS_CHAT_ID

review_router = Router()


class ReviewForm(StatesGroup):
    waiting_for_text = State()


# Открытие меню отзывов
@review_router.message(F.text == "⭐ Отзывы")
async def show_reviews_menu(message: Message):
    await message.answer("📢 Меню отзывов:", reply_markup=reviews_menu)


# Кнопка "Все отзывы" (пересылаем ссылку на канал)
@review_router.message(F.text == "📖 Все отзывы")
async def all_reviews(message: Message):
    await message.answer("📝 Все отзывы можно посмотреть здесь: @hakune_reviews")


# Кнопка "Оставить отзыв"
@review_router.message(F.text == "📝 Оставить отзыв")
async def leave_review(message: Message, state: FSMContext):
    await message.answer("✍️ Напиши свой отзыв и прикрепи фото/видео/гиф, если хочешь.",
                         reply_markup=ReplyKeyboardRemove())
    await state.set_state(ReviewForm.waiting_for_text)


# Приём текста/медиа отзыва
@review_router.message(ReviewForm.waiting_for_text)
async def process_review(message: Message, state: FSMContext):
    username = message.from_user.username or message.from_user.full_name

    header = f"📢 Отзыв от @{username}:"

    try:
        # Если есть медиа
        if message.photo:
            await message.bot.send_photo(REVIEWS_CHAT_ID, message.photo[-1].file_id,
                                         caption=f"{header}\n{message.caption or ''}")
        elif message.video:
            await message.bot.send_video(REVIEWS_CHAT_ID, message.video.file_id,
                                         caption=f"{header}\n{message.caption or ''}")
        elif message.animation:
            await message.bot.send_animation(REVIEWS_CHAT_ID, message.animation.file_id,
                                             caption=f"{header}\n{message.caption or ''}")
        else:
            await message.bot.send_message(REVIEWS_CHAT_ID, f"{header}\n{message.text}")

        await message.answer("✅ Спасибо! Твой отзыв отправлен.", reply_markup=main_menu("client"))
    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке отзыва: {e}", reply_markup=main_menu("client"))

    await state.clear()


# Кнопка "Назад"
@review_router.message(F.text == "⬅️ Назад")
async def back_to_main(message: Message):
    await message.answer("🏠 Главное меню:", reply_markup=main_menu("client"))

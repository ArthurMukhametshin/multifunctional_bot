import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from states.user_states import Feedback
from services import google_sheets as gs

router = Router()

@router.callback_query(F.data.startswith("rate_"))
async def process_rating(callback: CallbackQuery, state: FSMContext):
    """
    Ловит нажатие на кнопку с оценкой, сохраняет ее и запрашивает текстовый отзыв.
    """
    rating = int(callback.data.split("_")[1])
    order_id = int(callback.data.split("_")[2])

    # Получаем данные о мероприятии из Google Sheets, чтобы передать их дальше
    from database import get_order_by_id
    order = await get_order_by_id(order_id)
    event = await gs.get_event_by_id_from_sheet(order[2])

    await state.update_data(rating=rating, event_name=event['ShortName'])
    await state.set_state(Feedback.waiting_for_text)

    await callback.message.edit_text(f"спасибо за оценку! теперь, пожалуйста, напиши свой отзыв в свободной форме")
    await callback.answer()


@router.message(Feedback.waiting_for_text)
async def process_feedback_text(message: Message, state: FSMContext):
    """
    Получает текстовый отзыв, записывает все в Google Sheets и завершает диалог.
    """
    user_data = await state.get_data()
    rating = user_data.get('rating')
    event_name = user_data.get('event_name')
    feedback_text = message.text

    # Записываем отзыв в Google Sheets
    await gs.add_feedback_to_sheet(
        user_id=message.from_user.id,
        event_name=event_name,
        rating=rating,
        text=feedback_text
    )

    await message.answer("спасибо большое за твой отзыв! он поможет нам стать еще лучше ✨")
    await state.clear()
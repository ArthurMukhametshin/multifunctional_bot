import os
from aiogram import Bot
from aiogram.types import InputFile
from aiogram.types import BufferedInputFile

async def send_arrival_info(bot: Bot, user_id: int, user_name: str, event: dict, order_id: int = None):
    """Отправляет инструкцию, как добраться до места."""
    if order_id:
        from database import get_order_by_id
        order = await get_order_by_id(order_id)
        if not order or order[4] != 'paid':
            return

    time_str = event['datetime_obj'].strftime('%H:%M')

    # Формируем текст с Markdown-ссылками и цитатой
    text = (
        f"привет, {user_name}!🪴\n"
        f"с заботой напоминаю тебе о мероприятии «{event['ShortName']}» завтра в {time_str} по адресу: Павла Андреева, 23с12\n\n"
        "мы очень просим тебя не опаздывать, чтобы не пропустить ничего интересного!\n\n"
        "чтобы быстрее найти нас, прикрепляю точку входа на территорию (нужно зайти через пункт охраны) — <a href='https://yandex.ru/maps/?whatshere%5Bzoom%5D=21&whatshere%5Bpoint%5D=37.621582,55.720705&si=5vp0w007x3hy77w2jqwfghpc64'>тут</a>\n\n"
        "а также маршрут по территории до входа в наш корпус — <a href='https://yandex.ru/maps?rtext=55.720695,37.621594~55.719678,37.621576&rtt=mt'>тут</a>\n\n"
        "и конечно же передаю в твои руки ценный видеомаршрут!🗝️"
    )

    # Отправляем основной текст
    await bot.send_message(user_id, text)

    # Отправляем видео
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    video_path = os.path.join(base_dir, 'arrival_video.mp4')

    with open(video_path, "rb") as video_file:
        video = BufferedInputFile(video_file.read(), filename="arrival_video.mp4")
        await bot.send_video(user_id, video)

    # Отправляем текст
    quote_text = (
        "<blockquote>минутка фактов:\n"
        "мы находимся в историческом месте — бывшая территория известного парфюмерного завода «Новая Заря», основанного в 1864 году Генрихом Брокаром</blockquote>"
    )
    await bot.send_message(user_id, quote_text, parse_mode="HTML")


async def request_feedback(bot: Bot, user_id: int, order_id: int):
    """Запрашивает у пользователя отзыв о мероприятии."""
    from database import get_order_by_id
    from keyboards.inline import feedback_rating_keyboard

    order = await get_order_by_id(order_id)
    # Отправляем запрос только если билет все еще активен
    if order and order[4] == 'paid':
        await bot.send_message(
            user_id,
            "привет! надеемся, тебе понравилось на нашем мероприятии\n\n"
            "пожалуйста, оцени его от 1 до 5, это очень нам поможет!",
            reply_markup=feedback_rating_keyboard(order_id)
        )
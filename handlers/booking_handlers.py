import logging
import os
import uuid
from bot import scheduler
from datetime import datetime, timedelta
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from yookassa import Configuration, Payment
from config_reader import config
import database as db
from keyboards import inline as kb
from services import google_sheets as gs
from services.ticket_generator import generate_ticket_image
from states.user_states import Booking
from utils.scheduler import request_feedback, send_arrival_info

router = Router()

Configuration.account_id = config.yookassa_shop_id.get_secret_value()
Configuration.secret_key = config.yookassa_secret_key.get_secret_value()

async def issue_ticket(callback: CallbackQuery, bot: Bot, order_id: int, event: dict, price: int, promo_code: str | None, original_price: int, payment_id: str):
    """
    Общая логика выдачи билета с правильным текстом для всех сценариев.
    """

    user_db_info = await db.get_user_by_id(callback.from_user.id)
    full_name = user_db_info[2] if user_db_info else "Гость"
    phone_number = user_db_info[3] if user_db_info else "Не указан"

    date_str = event['datetime_obj'].strftime('%d.%m.%Y в %H:%M')
    ticket_path = generate_ticket_image(
        event_name=event['ShortName'], fio=full_name, date_str=date_str, address="ул. Павла Андреева, д. 23 с. 12"
    )

    if not ticket_path:
        await bot.send_message(callback.from_user.id,
                               "упс, не получилось создать твой билетик. пожалуйста, напиши в службу заботы @cotvorenie_space")
        return

    await gs.add_client_to_sheet(user_id=callback.from_user.id, username=callback.from_user.username,
                                 full_name=full_name, phone_number=phone_number)
    await gs.add_order_to_sheet(order_id=order_id, user_id=callback.from_user.id, event_name=event['ShortName'],
                                event_date=event['DateTime'], amount=price, status='оплачено', promo_code=promo_code)

    caption_text = ""

    # СЦЕНАРИЙ 1: Билет по программе лояльности
    if payment_id == 'loyalty_program':
        await db.reset_loyalty_count(callback.from_user.id)
        caption_text = (
            f"твой бесплатный билетик на «{event['ShortName']}» готов!\n\n"
            "счетчик лояльности обнулен, начинаем копить снова!\n\n"
        )

    # СЦЕНАРИЙ 2: Билет был ОПЛАЧЕН реальными деньгами (цена > 0)
    elif price > 0:
        await db.increment_loyalty_count(callback.from_user.id)
        loyalty_count_after = await db.get_loyalty_count(callback.from_user.id)
        caption_text = (
            f"твой билетик на «{event['ShortName']}» готов!\n\n"
            f"+1 балл в программе лояльности, теперь у тебя {loyalty_count_after} из 5!\n\n"
        )

    # СЦЕНАРИЙ 3: Билет бесплатный (изначально или из-за промокода), но НЕ по лояльности
    else:
        caption_text = f"твой билетик на бесплатное мероприятие «{event['ShortName']}» готов!\n\n"

    caption_text += "возврат возможен не позднее чем за 48 часов до начала мероприятия.\n\nсохрани его и покажи на входе охране. до встречи!"

    photo = FSInputFile(ticket_path)
    await bot.send_photo(callback.from_user.id, photo, caption=caption_text, parse_mode="Markdown")

    try:
        os.remove(ticket_path)
    except OSError as e:
        logging.error(f"Ошибка при удалении файла билета {ticket_path}: {e}")

    time_until_event = event['datetime_obj'] - datetime.now()
    if time_until_event.total_seconds() < 24 * 3600:
        await send_arrival_info(bot, callback.from_user.id, callback.from_user.first_name, event, order_id)
    else:
        run_date_24h = event['datetime_obj'] - timedelta(hours=24)
        scheduler.add_job(send_arrival_info, trigger='date', run_date=run_date_24h,
                          kwargs={'bot': bot, 'user_id': callback.from_user.id,
                                  'user_name': callback.from_user.first_name, 'event': event, 'order_id': order_id})
        await bot.send_message(callback.from_user.id,
                               "за 24 часа до начала мы вышлем подробную инструкцию, как нас найти. не потеряешься! 😉")

    feedback_date = event['datetime_obj'] + timedelta(hours=18)
    scheduler.add_job(
        request_feedback,
        trigger='date',
        run_date=feedback_date,
        kwargs={'bot': bot, 'user_id': callback.from_user.id, 'order_id': order_id}
    )
    logging.info(f"Запланирован запрос отзыва для заказа #{order_id} на {feedback_date}")

@router.callback_query(F.data == "events")
async def show_events_afisha(callback: CallbackQuery):
    """
    Показывает пользователю афишу — список мероприятий из Google Таблицы.
    Каждое мероприятие — это кнопка с коротким названием.
    """
    # Получаем актуальные мероприятия из Google Sheets
    events = gs.get_events_from_sheet()

    if not events:
        await callback.message.edit_text(
            "упс! я в спячке, напиши в службу заботы @cotvorenie_space",
            reply_markup=kb.main_menu()
        )
        return

    await callback.message.edit_text(
        "что сотворим?\n\nвыбирай:",
        reply_markup=kb.events_keyboard(events),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("event_"))
async def show_event_details(callback: CallbackQuery):
    """
    Показывает подробную информацию о выбранном мероприятии.
    Перед этим проверяет, не куплен ли уже билет.
    """
    event_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    has_ticket = await db.check_if_ticket_exists(user_id, event_id)
    event = await gs.get_event_by_id_from_sheet(event_id)

    if not event:
        await callback.answer("Мероприятие не найдено.", show_alert=True)
        return

    event_date_str = event['datetime_obj'].strftime('%d.%m.%Y')
    event_time_str = event['datetime_obj'].strftime('%H:%M')

    text = ""
    reply_markup = None

    if has_ticket:
        text = (
            f"**{event['ShortName']}**\n\n"
            f"дата: {event_date_str}\n"
            f"время: {event_time_str}\n\n"
            "у тебя уже есть билетик на это событие! "
            "можешь посмотреть его в разделе «посмотрю мои билеты»"
        )
        reply_markup = kb.already_booked_keyboard()
    else:
        # ИСПОЛЬЗУЕМ ОДИНАРНЫЕ КАВЫЧКИ ДЛЯ КЛЮЧА 'Price'
        price_text = 'бесплатно' if event['Price'] == 0 else f"{event['Price']} руб."

        text = (
            f"**{event['ShortName']}**\n\n"
            f"дата: {event_date_str}\n"
            f"время: {event_time_str}\n"
            f"стоимость: {price_text}\n\n"
            f"{event['Description']}"
        )
        reply_markup = kb.event_details_keyboard(event_id)

    await callback.message.edit_text(
        text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("buy_"))
async def start_booking_process(callback: CallbackQuery, state: FSMContext):
    """
    Запускается после нажатия "Купить билет".
    Проверяет программу лояльности и запрашивает ФИО.
    """
    event_id = int(callback.data.split("_")[1])
    event = await gs.get_event_by_id_from_sheet(event_id)

    if not event:
        await callback.answer("Мероприятие не найдено.", show_alert=True)
        return

    # Сохраняем данные о мероприятии в состояние FSM
    await state.update_data(
        event_id=event['ID'],
        event_name=event['ShortName'],
        price=event['Price'],
        original_price=event['Price']
    )

    # Проверяем программу лояльности (6-й билет в подарок)
    loyalty_count = await db.get_loyalty_count(callback.from_user.id)

    if loyalty_count >= 5:
        await state.update_data(price=0, is_loyalty_ticket=True)
        text = (
            f"🎉 поздравляем! ты накопил {loyalty_count} посещений, и это мероприятие для тебя бесплатное!\n\n"
            f"мероприятие: {event['ShortName']}\n\n"
            "для оформления бесплатного билетика, пожалуйста, напиши свое ФИО"
        )
    else:
        await state.update_data(is_loyalty_ticket=False)
        text = (
            f"твой выбор — в самое сердце!\n\nдля получения билета на «{event['ShortName']}» напиши свое ФИО\n\n"
            # f"💡 *Осталось накопить {remaining} платных посещений до бесплатного билета!*"
        )

    # Редактируем прошлое сообщение, чтобы не было "прыжков" в интерфейсе
    await callback.message.edit_text(text, parse_mode="Markdown")
    await state.set_state(Booking.entering_name)
    await callback.answer()

@router.message(Booking.entering_name)
async def enter_name(message: Message, state: FSMContext):
    """Получает ФИО и запрашивает телефон."""
    await state.update_data(full_name=message.text)
    await message.answer("супер! оставишь свой номерок?")
    await state.set_state(Booking.entering_phone)

@router.message(Booking.entering_phone)
async def enter_phone(message: Message, state: FSMContext):
    """Получает телефон и спрашивает про промокод."""
    await state.update_data(phone_number=message.text)

    # Сохраняем контакты в БД
    user_data = await state.get_data()
    await db.update_user_contacts(message.from_user.id, user_data['full_name'], user_data['phone_number'])

    # Теперь не просим подтверждения, а спрашиваем про промокод
    await message.answer(
        "отлично! у тебя есть промокод на скидку? 😑",
        reply_markup=kb.promo_code_keyboard()
    )
    await state.set_state(Booking.waiting_for_promo)

@router.callback_query(Booking.waiting_for_promo, F.data == "has_promo")
async def ask_for_promo_code(callback: CallbackQuery, state: FSMContext):
    """Запрашивает ввод промокода."""
    await callback.message.edit_text("введи, пожалуйста, промокод:")
    await state.set_state(Booking.entering_promo_code)
    await callback.answer()

@router.message(Booking.entering_promo_code)
async def process_promo_code(message: Message, state: FSMContext):
    """
    Проверяет промокод в ПРАВИЛЬНОМ порядке и корректно обрабатывает все ошибки.
    """
    promo_code = message.text.strip().upper()
    promo_details = await gs.get_promo_details(promo_code)

    error_message = None

    # 1. Проверка №1: Существует ли такой промокод в принципе?
    if not promo_details:
        error_message = "увы, такой промокод не найден или уже не действует. продолжаем без скидки 🥲"

    # 2. Проверка №2 (только для реферальных кодов): Не пытается ли владелец использовать свой код?
    # Эта проверка идет ДО проверки статуса, потому что она важнее.
    elif promo_details.get('type') == 'referral_invite' and promo_details.get('owner_id') == message.from_user.id:
        error_message = "этот промокод предназначен для твоего друга. ты не можешь использовать его сам! 😉"

    # 3. Проверка №3: Активен ли промокод? (не был ли он уже использован)
    elif promo_details.get('status') != 'active':
        error_message = "этот промокод уже был использован. продолжаем без скидки 🥲"

    # Если была какая-либо ошибка, отправляем соответствующее сообщение и переходим к итогам
    if error_message:
        await message.answer(error_message)
        await show_confirmation_summary(message, state)
        return

    # Если мы дошли до сюда, значит, все проверки пройдены и код корректен
    user_data = await state.get_data()
    original_price = user_data.get('price')
    discount = promo_details['discount']
    new_price = int(original_price * (1 - discount / 100))

    await state.update_data(price=new_price, promo_code=promo_code, promo_details=promo_details)
    await message.answer(f"промокод принят! твоя скидка — {discount}%. новая цена: {new_price} руб.")

    await show_confirmation_summary(message, state)

# 3. ОБРАБОТЧИК ДЛЯ КНОПКИ "ПРОДОЛЖИТЬ БЕЗ ПРОМОКОДА"
@router.callback_query(Booking.waiting_for_promo, F.data == "no_promo")
async def no_promo_code(callback: CallbackQuery, state: FSMContext):
    """Пропускает шаг с промокодом и переходит к подтверждению."""
    await callback.message.delete()  # Удаляем сообщение с кнопками
    await show_confirmation_summary(callback.message, state)  # Вызываем общую функцию подтверждения
    await callback.answer()

# 4. ВЫНОСИМ ЛОГИКУ ПОДТВЕРЖДЕНИЯ В ОТДЕЛЬНУЮ ФУНКЦИЮ
async def show_confirmation_summary(message: Message, state: FSMContext):
    """
    Показывает итоговые данные перед оплатой.
    Вызывается либо после ввода промокода, либо после отказа от него.
    """
    user_data = await state.get_data()
    promo_code_info = f"\nпромокод: {user_data['promo_code']}" if 'promo_code' in user_data else ""

    price_text = 'бесплатно' if user_data['price'] == 0 else f"{user_data['price']} руб."

    text = (
        "пожалуйста, проверь данные:\n"
        f"мероприятие: **{user_data['event_name']}**\n"
        f"ФИО: {user_data['full_name']}\n"
        f"телефон: {user_data['phone_number']}{promo_code_info}\n"
        f"итоговая стоимость: **{price_text}**\n\n"
        "нажимая кнопку ниже, ты соглашаешься с Политикой конфиденциальности"
    )

    await message.answer(
        text,
        reply_markup=kb.confirm_booking_keyboard(user_data['event_id']),
        parse_mode="Markdown"
    )
    await state.set_state(Booking.confirming_data)

@router.callback_query(Booking.confirming_data, F.data.startswith("book_"))
async def confirm_booking(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Создает платеж в ЮKassa или выдает бесплатный билет."""
    await callback.answer()

    user_data = await state.get_data()
    price = user_data.get('price')
    original_price = user_data.get('original_price')
    promo_code = user_data.get('promo_code')
    is_loyalty = user_data.get('is_loyalty_ticket', False)

    event = await gs.get_event_by_id_from_sheet(user_data['event_id'])

    # Сценарий 1: Бесплатный билет
    if price == 0:
        await callback.message.edit_text("оформляем твой бесплатный билетик...")

        # --- НОВАЯ, НАДЕЖНАЯ ЛОГИКА ОПРЕДЕЛЕНИЯ ТИПА ---
        payment_id_for_db = 'loyalty_program' if is_loyalty else 'generated_ticket'

        order_id = await db.create_order(callback.from_user.id, user_data['event_id'], 0)
        await db.update_order_status(order_id, payment_id_for_db, 'paid')

        await issue_ticket(
            callback=callback, bot=bot, order_id=order_id, event=event, price=0,
            promo_code=promo_code, original_price=original_price, payment_id=payment_id_for_db
        )
        await state.clear()
        return

    # СЦЕНАРИЙ 2: Платный билет
    order_id = await db.create_order(callback.from_user.id, user_data['event_id'], price)

    try:
        payment = Payment.create({
            "amount": {"value": f"{price}.00", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": f"https://t.me/{(await bot.get_me()).username}"},
            "capture": True,
            "description": f"Билет на «{user_data['event_name']}». Заказ #{order_id}",
            "metadata": {"order_id": order_id, "promo_code": promo_code}
        }, uuid.uuid4())

        await db.update_order_payment_id(order_id, payment.id)

        await callback.message.edit_text(
            "отлично! остался последний шаг — оплата 💰\n\n"
            "нажми на кнопку ниже, чтобы перейти на страницу оплаты. после успешной оплаты вернись в бот и нажми «я оплатил, проверить»",
            reply_markup=kb.payment_keyboard(payment.confirmation.confirmation_url, payment.id)
        )
        await state.clear()

    except Exception as e:
        logging.error(f"Ошибка создания платежа для заказа #{order_id}: {e}")
        await callback.message.edit_text(
            "упс, не получилось создать ссылку на оплату. попробуй снова или напиши в службу заботы @cotvorenie_space")
        await state.clear()

@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(callback: CallbackQuery, bot: Bot):
    """
    Проверяет статус платежа в ЮKassa после нажатия кнопки "я оплатил".
    Если оплата прошла, выдает билет и выполняет все связанные действия.
    """
    await callback.answer("проверяю статус платежа...")
    payment_id = callback.data.split("_")[2]

    try:
        payment_info = Payment.find_one(payment_id)
    except Exception as e:
        logging.error(f"Ошибка проверки платежа {payment_id}: {e}")
        await callback.answer("Не удалось проверить статус платежа. Попробуйте снова через минуту.", show_alert=True)
        return

    if payment_info.status == 'succeeded':
        order_id = int(payment_info.metadata['order_id'])
        order = await db.get_order_by_id(order_id)

        if order and order[4] == 'paid':
            await callback.answer("Этот билет уже был выдан.", show_alert=True)
            return

        await callback.message.edit_text("✔️ оплата прошла успешно! сейчас я пришлю твой билетик...")
        # Обновляем статус в нашей внутренней БД на 'paid'
        await db.update_order_status(order_id, payment_id, 'paid')

        reward_code = None

        promo_code = payment_info.metadata.get('promo_code')
        if promo_code:
            promo_details = await gs.get_promo_details(promo_code)
            if promo_details and promo_details['type'] == 'referral_invite':
                reward_code = await gs.activate_referral_code(
                    row_index=promo_details['row_index'],
                    friend_user_id=callback.from_user.id,
                    friend_order_id=order_id
                )

        if reward_code:
            try:
                await bot.send_message(
                    chat_id=promo_details['owner_id'],
                    text=f"ура! твой друг воспользовался приглашением. вот твоя награда — промокод на 20% скидки: `{reward_code}`",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logging.error(f"Не удалось отправить наградной код пользователю {promo_details['owner_id']}: {e}")

        event = await gs.get_event_by_id_from_sheet(order[2])
        price = order[5]
        original_price = event['Price']

        # Вызываем нашу общую вспомогательную функцию для выдачи билета
        await issue_ticket(callback, bot, order_id, event, price, promo_code, original_price, payment_id)

    elif payment_info.status == 'pending':
        await callback.answer("платеж еще не прошел. подожди минутку и попробуй снова 🥹", show_alert=True)


    else:
        await callback.message.edit_text(
            f"платеж не прошел (статус: {payment_info.status}) 🥲\n\nпопробуй создать заказ заново из афиши"

        )
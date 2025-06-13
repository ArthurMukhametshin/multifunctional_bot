import logging
import os
from datetime import datetime
import uuid
from yookassa import Refund
from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, FSInputFile, Message
import database as db
from keyboards import inline as kb
from services import google_sheets as gs
from config_reader import config
from utils import faq_data
from states.user_states import Checklists
from aiogram.fsm.context import FSMContext

router = Router()

def get_welcome_text(user_name: str) -> str:
    """Генерирует приветственный текст для главного меню."""
    return (
        f"привет, {user_name}!\n\n"
        "это бот арт-пространства со-творение🪽\n\n"
        "я принес тебе меню, что будешь?"
    )

def create_progress_bar(count: int) -> str:
    """Создает текстовый прогресс-бар с котом и счетчиком."""
    if count >= 5:
        progress = "■" * 5
        cat_emoji = "🎉"
        return f"[{progress}] 5 из 5 {cat_emoji}\nпоздравляем, ты набрал 5 баллов! можешь взять бесплатный билетик на любое мероприятие!"
    else:
        filled = "■" * count
        empty = "□" * (5 - count)
        cat_emoji = "🐈"
        return f"[{filled}{empty}] {count} из 5 {cat_emoji}"

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    await db.add_user(message.from_user.id, message.from_user.username)
    await message.answer(
        get_welcome_text(message.from_user.first_name),
        reply_markup=kb.main_menu()
    )

@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery):
    """
    Универсальный обработчик для возврата в главное меню.
    Удаляет текущее сообщение и отправляет новое.
    """
    await callback.message.delete()

    await callback.message.answer(
        get_welcome_text(callback.from_user.first_name),
        reply_markup=kb.main_menu()
    )
    await callback.answer()

@router.callback_query(F.data == "loyalty_info")
async def show_loyalty_info(callback: CallbackQuery):
    user_id = callback.from_user.id
    loyalty_count = await db.get_loyalty_count(user_id)
    progress_bar = create_progress_bar(loyalty_count)

    caption = (
        "креативная система лояльности «со-творение»:\n\n"
        "сотвори с другом — и получите оба по 20% скидки!\n\n"
        "посети 5 мероприятий — и получи 6-е в подарок!\n\n"
        "тайна старого сейфа:\n"
        "за каждое посещение мероприятия получи попытку открыть кодовый замок старого сейфа, а что там внутри — неизвестно, узнаешь?\n\n"
        f"{progress_bar}"
    )

    photo = FSInputFile("loyalty.jpg")
    await callback.message.answer_photo(
        photo=photo, caption=caption, reply_markup=kb.loyalty_info_keyboard()
    )
    await callback.message.delete()
    await callback.answer()

@router.callback_query(F.data == "manage_tickets")
async def show_my_tickets_list(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_orders = await db.get_user_paid_orders(user_id)

    if not user_orders:
        await callback.message.edit_text(
            "у тебя пока нет билетиков, но ты можешь это исправить, заглянув в афишу!",
            reply_markup=kb.main_menu()
        )
        return

    orders_with_events = []
    for order in user_orders:
        event = await gs.get_event_by_id_from_sheet(order[2])
        if event:
            orders_with_events.append((order, event))

    await callback.message.edit_text(
        "вот твои билетики! нажми на любой, чтобы посмотреть детали или отменить запись",
        reply_markup=kb.my_tickets_list_keyboard(orders_with_events)
    )

@router.callback_query(F.data.startswith("view_ticket_"))
async def show_ticket_details(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    order = await db.get_order_by_id(order_id)
    event = await gs.get_event_by_id_from_sheet(order[2])

    event_date_str = event['datetime_obj'].strftime('%d.%m.%Y')
    event_time_str = event['datetime_obj'].strftime('%H:%M')

    text = (
        f"твой билетик на мероприятие:\n"
        f"**{event['ShortName']}**\n"
        f"дата: {event_date_str}\n"
        f"время: {event_time_str}\n\n"
        "хочешь отменить запись?\n"
        "возврат возможен не позднее чем за 48 часов!"
    )
    await callback.message.edit_text(text, reply_markup=kb.ticket_actions_keyboard(order_id), parse_mode="Markdown")

@router.callback_query(F.data.startswith("confirm_cancel_"))
async def confirm_cancellation_prompt(callback: CallbackQuery):
    """
    Запрашивает подтверждение отмены, но сначала проверяет, не истекло ли время.
    """
    order_id = int(callback.data.split("_")[2])
    order = await db.get_order_by_id(order_id)
    event = await gs.get_event_by_id_from_sheet(order[2])

    time_diff = event['datetime_obj'] - datetime.now()
    if time_diff.total_seconds() <= 48 * 3600:
        await callback.answer("упс, до мероприятия осталось менее 48 часов, отмена уже невозможна 🥲", show_alert=True)
        return

    await callback.message.edit_text(
        "ты точно уверен, что хочешь отменить запись? это действие необратимо...",
        reply_markup=kb.confirm_cancellation_keyboard(order_id)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("final_cancel_"))
async def final_cancel_booking(callback: CallbackQuery):
    """
    Финальная отмена билета с проверкой времени, возвратом средств через ЮKassa
    и корректной логикой возврата/списания баллов.
    """
    await callback.answer("обрабатываю отмену...")

    order_id = int(callback.data.split("_")[2])
    order = await db.get_order_by_id(order_id)
    if not order:
        await callback.message.edit_text("Ошибка: не удалось найти информацию о заказе.")
        return

    event = await gs.get_event_by_id_from_sheet(order[2])
    if not event:
        await callback.message.edit_text("Ошибка: не удалось найти информацию о мероприятии.")
        return

    # 1. Проверяем, можно ли отменить билет
    time_diff = event['datetime_obj'] - datetime.now()
    if time_diff.total_seconds() <= 48 * 3600:
        await callback.answer("упс, до мероприятия осталось менее 48 часов, отмена уже невозможна 🥲", show_alert=True)
        await callback.message.edit_text(
            "К сожалению, время для отмены этого билета истекло.",
            reply_markup=kb.ticket_actions_keyboard(order_id)
        )
        return

    payment_id_from_db = order[3]
    amount = str(order[5])
    confirmation_text = ""

    # 2. Обрабатываем отмену в зависимости от типа билета

    # СЦЕНАРИЙ 1: Отменяется билет, полученный по программе лояльности.
    if payment_id_from_db == 'loyalty_program':
        await db.set_loyalty_points(callback.from_user.id, 5)
        confirmation_text = f"эх, твой бесплатный билетик отменен. мы вернули тебе 5 баллов лояльности, можешь использовать их на другое мероприятие! ✨"

    # СЦЕНАРИЙ 2: Отменяется платный билет (цена > 0).
    elif float(amount) > 0:
        try:
            idempotence_key = str(uuid.uuid4())
            refund = Refund.create({
                "amount": {"value": amount, "currency": "RUB"},
                "payment_id": payment_id_from_db
            }, idempotence_key)

            if refund.status == 'succeeded' or refund.status == 'pending':
                await db.decrement_loyalty_count(callback.from_user.id)
                confirmation_text = f"эх, твой билетик на '{event['ShortName']}' отменен и деньги скоро вернутся!\n\nодин балл лояльности за этот билет забрали 🥲"
            else:
                confirmation_text = f"не удалось оформить возврат (статус ЮKassa: {refund.status}). пожалуйста, обратись в службу заботы"

        except Exception as e:
            logging.error(f"Ошибка возврата ЮKassa для заказа #{order_id}: {e}")
            confirmation_text = "какие-то странности при оформлении возврата. обратись, пожалуйста, в службу заботы @cotvorenie_space"

    # СЦЕНАРИЙ 3: Отменяется билет на изначально бесплатное мероприятие.
    else:
        confirmation_text = f"запись на бесплатное мероприятие '{event['ShortName']}' отменена!"

    # 3. Обновляем статусы в наших системах в любом успешном случае
    if "ошибка" not in confirmation_text and "Не удалось" not in confirmation_text:
        await db.update_order_status(order_id, 'cancelled_by_user', 'cancelled')
        await gs.update_order_status_in_sheet(order_id, 'возврат')

    # 4. Отправляем финальное сообщение пользователю
    await callback.message.edit_text(confirmation_text)

@router.callback_query(F.data == "get_checklist")
async def get_checklist(callback: CallbackQuery, state: FSMContext):
    """
    Предлагает пользователю подписаться на канал для получения чек-листа.
    """
    await state.clear()

    await callback.message.edit_text(
        "супер, чек-лист почти у тебя! а ты уже подписался на наш канал?\n\n"
        "скорее подписывайся и нажимай кнопку «проверяй!»",
        reply_markup=kb.check_subscription_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "check_subscription")
async def check_subscription_and_show_list(callback: CallbackQuery, bot: Bot, state: FSMContext):
    user_channel_status = await bot.get_chat_member(chat_id=config.channel_id, user_id=callback.from_user.id)

    if user_channel_status.status != 'left':
        try:
            files = [f for f in os.listdir('checklists') if f.endswith('.pdf')]
            if not files:
                await callback.message.edit_text("упс, кажется, чек-листов пока нет. загляни чуть позже!",
                                                 reply_markup=kb.main_menu())
                return
            await state.update_data(checklist_files=files)
            await state.set_state(Checklists.choosing_checklist)

            await callback.message.edit_text(
                "благодарим за подписку! выбирай, что тебе по душе:",
                reply_markup=kb.checklists_keyboard(files)
            )
        except FileNotFoundError:
            await callback.message.edit_text("сундук с чек-листами где-то потерялся... мой босс скоро все исправит!",
                                             reply_markup=kb.main_menu())
    else:
        await callback.answer("эй! а ну-ка подпишись!\n\nбез труда не вынешь рыбку из пруда!", show_alert=True)


@router.callback_query(Checklists.choosing_checklist, F.data.startswith("checklist_"))
async def send_checklist_file(callback: CallbackQuery, state: FSMContext):
    try:
        file_index = int(callback.data.split("_")[1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка: неверный формат данных кнопки.", show_alert=True)
        return

    # Получаем список файлов из состояния
    user_data = await state.get_data()
    files = user_data.get('checklist_files')

    # Находим нужное имя файла по индексу
    if files and 0 <= file_index < len(files):
        file_name = files[file_index]
        file_path = os.path.join('checklists', file_name)

        if os.path.exists(file_path):
            document = FSInputFile(file_path)
            button_text = file_name.replace('.pdf', '').replace('_', ' ').capitalize()
            await callback.message.delete()
            await callback.message.answer_document(document, caption=f"держи чек-лист «{button_text}»!")
            await callback.answer()
        else:
            await callback.answer("не могу найти этот чек-лист... возможно, его удалили", show_alert=True)
    else:
        await callback.answer("не могу найти чек-листы... возможно, их удалили", show_alert=True)

    await state.clear()

@router.callback_query(F.data == "faq")
async def show_faq_list(callback: CallbackQuery):
    """
    Показывает список вопросов из FAQ.
    """
    await callback.message.edit_text(
        f"🫂 частые вопросы\n\n{faq_data.FAQ_FOOTER_TEXT}",
        reply_markup=kb.faq_list_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("faq_"))
async def show_faq_answer(callback: CallbackQuery):
    """
    Показывает ответ на выбранный вопрос.
    """
    question_key = callback.data.split("_", 1)[1]

    question_text, answer_text = faq_data.FAQ_DATA.get(question_key)

    if question_text and answer_text:
        full_text = f"{question_text}\n\n{answer_text}"
        await callback.message.edit_text(
            full_text,
            reply_markup=kb.faq_answer_keyboard(),
            parse_mode="HTML"
        )
    else:
        await callback.answer("простите, не могу ответить на этот вопрос...мне не сообщили актуальную информацию")

@router.callback_query(F.data == "invite_friend")
async def invite_friend(callback: CallbackQuery):
    """Генерирует реферальный код и отправляет его пользователю."""
    await callback.answer("создаю твой уникальный код...")
    referral_code = await gs.generate_and_add_referral_code(callback.from_user.id)

    if referral_code:
        await callback.message.edit_caption(
            caption=(
                "отлично! вот твой уникальный код для друга:\n\n"
                f"`{referral_code}`\n\n"
                "отправь его другу. как только он купит по нему билет со скидкой 20%, "
                "я пришлю тебе в этот чат твой личный промокод на скидку!"
            ),
            reply_markup=kb.loyalty_info_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await callback.answer("упс, не получилось создать код. попробуй, пожалуйста, спустя какое-то время или обратись в службу заботы 🙏", show_alert=True)
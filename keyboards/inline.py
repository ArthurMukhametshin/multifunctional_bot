from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config_reader import config
from utils import faq_data

def main_menu():
    buttons = [
        [InlineKeyboardButton(text="🎞️ посмотрю афишу мероприятий", callback_data="events")],
        [InlineKeyboardButton(text="🎟️ посмотрю мои билеты", callback_data="manage_tickets")],
        [InlineKeyboardButton(text="🗝️ узнаю о программе лояльности", callback_data="loyalty_info")],
        [InlineKeyboardButton(text="🫂 узнаю ответы на частые вопросы", callback_data="faq")],
        [InlineKeyboardButton(text="🖇️ получу креативные чек-листы", callback_data="get_checklist")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

def loyalty_info_keyboard():
    buttons = [
        [InlineKeyboardButton(text="← назад к меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def events_keyboard(events):
    """Клавиатура со списком мероприятий (краткие названия)."""
    buttons = []
    for event in events:
        buttons.append(
            [InlineKeyboardButton(text=event['ShortName'], callback_data=f"event_{event['ID']}")]
        )
    buttons.append([InlineKeyboardButton(text="← назад к меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def event_details_keyboard(event_id):
    """Клавиатура для детального просмотра: купить билет или назад."""
    buttons = [
        [InlineKeyboardButton(text="хочу свой билетик!", callback_data=f"buy_{event_id}")],
        [InlineKeyboardButton(text="← сотворю что-то другое", callback_data="events")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def confirm_booking_keyboard(event_id):
    buttons = [
        [InlineKeyboardButton(text="подтверждаю, возьми мои деньги!", callback_data=f"book_{event_id}")],
        [InlineKeyboardButton(text="← сотворю что-то другое", callback_data="events")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def check_subscription_keyboard():
    buttons = [
        [InlineKeyboardButton(text="подписаться на лучший канал", url=f"tg://resolve?domain={config.channel_username}")],
        [InlineKeyboardButton(text="готово, проверяй!", callback_data="check_subscription")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def checklists_keyboard(files: list):
    """Генерирует клавиатуру со списком чек-листов, используя ИНДЕКС в callback_data."""
    buttons = []
    for i, file_name in enumerate(files):
        button_text = file_name.replace('.pdf', '').replace('_', ' ').capitalize()
        buttons.append(
            [InlineKeyboardButton(text=f"📄 {button_text}", callback_data=f"checklist_{i}")]
        )
    buttons.append([InlineKeyboardButton(text="← назад к меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def my_tickets_list_keyboard(orders_with_events: list):
    """Клавиатура со списком купленных билетов."""
    buttons = []
    for order, event in orders_with_events:

        date_str = event['datetime_obj'].strftime('%d.%m.%Y')

        buttons.append([
            InlineKeyboardButton(
                text=f"{event['ShortName']} ({date_str})",
                callback_data=f"view_ticket_{order[0]}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="← назад к меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def ticket_actions_keyboard(order_id: int):
    """Клавиатура с действиями для конкретного билета."""
    buttons = [
        [InlineKeyboardButton(text="❌ отменить запись", callback_data=f"confirm_cancel_{order_id}")],
        [InlineKeyboardButton(text="← к списку билетов", callback_data="manage_tickets")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def confirm_cancellation_keyboard(order_id: int):
    """Клавиатура для финального подтверждения отмены."""
    buttons = [
        [InlineKeyboardButton(text="да, я точно уверен!", callback_data=f"final_cancel_{order_id}")],
        [InlineKeyboardButton(text="нет, я передумал", callback_data=f"view_ticket_{order_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def already_booked_keyboard():
    """Клавиатура для сообщения о том, что билет уже куплен."""
    buttons = [
        [InlineKeyboardButton(text="🎟️ посмотрю мои билеты", callback_data="manage_tickets")],
        [InlineKeyboardButton(text="← сотворю что-то другое", callback_data="events")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def faq_list_keyboard():
    """Создает клавиатуру со списком всех вопросов из FAQ_DATA."""
    buttons = []
    for key, (button_text, _) in faq_data.FAQ_DATA.items():
        buttons.append(
            [InlineKeyboardButton(text=button_text, callback_data=f"faq_{key}")]
        )
    buttons.append([InlineKeyboardButton(text="← назад к меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def faq_answer_keyboard():
    """Создает клавиатуру для ответа на вопрос (только кнопка "назад")."""
    buttons = [
        [InlineKeyboardButton(text="← вернуться к вопросам", callback_data="faq")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def feedback_rating_keyboard(order_id: int):
    """Клавиатура с оценками от 1 до 5."""
    buttons = [
        [
            InlineKeyboardButton(text=str(i), callback_data=f"rate_{i}_{order_id}") for i in range(1, 6)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def payment_keyboard(payment_url: str, payment_id: str):
    buttons = [
        [InlineKeyboardButton(text="→ перейти к оплате", url=payment_url)],
        [InlineKeyboardButton(text="✔️ я оплатил, проверить", callback_data=f"check_payment_{payment_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def promo_code_keyboard():
    """Клавиатура для шага с промокодом."""
    buttons = [
        [InlineKeyboardButton(text="у меня есть промокод! 🫰", callback_data="has_promo")],
        [InlineKeyboardButton(text="промокода нет 🥺", callback_data="no_promo")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def loyalty_info_keyboard():
    """Клавиатура под сообщением с информацией о программе лояльности."""
    buttons = [
        # --- НОВАЯ КНОПКА ---
        [InlineKeyboardButton(text="🫂 пригласить друга", callback_data="invite_friend")],
        [InlineKeyboardButton(text="← назад к меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
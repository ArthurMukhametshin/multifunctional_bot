import random
import string
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# Настройки доступа
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

# Путь к JSON-ключу
CREDS_FILE = 'service_account.json'
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
client = gspread.authorize(creds)
SHEET_NAME = "со-творение"
spreadsheet = client.open(SHEET_NAME)

# Название листов
WORKSHEET_AFISHA = "Афиша"
WORKSHEET_CLIENTS = "Клиенты"
WORKSHEET_ORDERS = "Заказы"
WORKSHEET_FEEDBACK = "Отзывы"
WORKSHEET_PROMOCODES = "Промокоды"
WORKSHEET_REFERRALS = "Рефералы"

# Открываем таблицу
spreadsheet = client.open(SHEET_NAME)
worksheet = spreadsheet.worksheet(WORKSHEET_AFISHA)

def get_events_from_sheet():
    """Получает список всех актуальных мероприятий из Google Таблицы."""
    all_events = worksheet.get_all_records()  # Получаем все записи как список словарей

    actual_events = []
    now = datetime.now()

    for event in all_events:
        try:
            # Преобразуем строку с датой в объект datetime
            event_date = datetime.strptime(event['DateTime'], '%d.%m.%Y %H:%M')
            # Добавляем в список только те мероприятия, которые еще не прошли
            if event_date > now:
                event['datetime_obj'] = event_date  # Сохраняем объект datetime для дальнейшей работы
                actual_events.append(event)
        except (ValueError, TypeError):
            # Пропускаем строки с некорректным форматом даты
            print(f"Неверный формат даты для мероприятия ID {event.get('ID', 'N/A')}")
            continue

    return actual_events


async def get_event_by_id_from_sheet(event_id: int):
    """Находит одно мероприятие по его ID."""
    all_events = get_events_from_sheet()
    for event in all_events:
        if event['ID'] == event_id:
            return event
    return None


async def add_client_to_sheet(user_id, username, full_name, phone_number):
    """Добавляет нового клиента или обновляет данные существующего, НЕ трогая дату регистрации."""
    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_CLIENTS)

        # Ищем пользователя по ID в первом столбце
        # Метод find вернет объект ячейки, если найдет, или None, если не найдет
        cell = worksheet.find(str(user_id), in_column=1)

        # Если cell is None, значит такого UserID в таблице еще нет
        if not cell:
            # ЕСЛИ ПОЛЬЗОВАТЕЛЬ НОВЫЙ
            # Генерируем дату регистрации и добавляем всю строку
            registration_date = datetime.now().strftime('%d.%m.%Y %H:%M')
            row_data = [user_id, username, full_name, phone_number, registration_date]
            worksheet.append_row(row_data)
        # Если cell существует, то мы просто ничего не делаем.
        # Это и есть наша логика: "не обновлять".

    except Exception as e:
        print(f"Ошибка при записи клиента в Google Sheets: {e}")

async def add_order_to_sheet(order_id, user_id, event_name, event_date, amount, status, promo_code=None):
    """Добавляет новый заказ в лист 'Заказы'."""
    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_ORDERS)
        created_at = datetime.now().strftime('%d.%m.%Y %H:%M')

        # --- Убеждаемся, что данные соответствуют 8 столбцам ---
        # OrderID, UserID, EventName, EventDate, Amount, Status, PromoCode, CreatedAt
        row_data = [
            order_id,
            user_id,
            event_name,
            event_date,
            amount,
            status,
            promo_code or '',  # Если промокода нет, вставляем пустую строку
            created_at
        ]
        worksheet.append_row(row_data)
    except Exception as e:
        print(f"Ошибка при записи заказа в Google Sheets: {e}")

async def update_order_status_in_sheet(order_id: int, new_status: str):
    """Обновляет статус заказа в листе 'Заказы'."""
    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_ORDERS)
        # Находим ячейку с нужным ID заказа (предполагается, что ID в первом столбце)
        cell = worksheet.find(str(order_id), in_column=1)

        if cell:
            # Обновляем ячейку в столбце "Статус" (предполагается, что это 6-й столбец, F)
            worksheet.update_cell(cell.row, 6, new_status)
    except Exception as e:
        print(f"Ошибка при обновлении статуса заказа {order_id} в Google Sheets: {e}")

async def add_feedback_to_sheet(user_id, event_name, rating, text):
    """Добавляет отзыв в лист 'Отзывы'."""
    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_FEEDBACK)
        created_at = datetime.now().strftime('%d.%m.%Y %H:%M')
        row_data = [user_id, event_name, rating, text, created_at]
        worksheet.append_row(row_data)
    except Exception as e:
        print(f"Ошибка при записи отзыва в Google Sheets: {e}")

WORKSHEET_PROMOCODES = "Промокоды"

async def get_promo_details(promo_code: str) -> dict | None:
    """Ищет промокод на правильном листе в зависимости от его префикса."""
    promo_code = promo_code.strip().upper()

    # Сценарий 1: Реферальный код для друга
    if promo_code.startswith("FRIEND-"):
        try:
            worksheet = spreadsheet.worksheet(WORKSHEET_REFERRALS)
            cell = worksheet.find(promo_code, in_column=1)
            if cell:
                # Проверяем, что статус 'generated' (еще не использован)
                status = worksheet.cell(cell.row, 5).value
                if status == 'generated':
                    owner_id = int(worksheet.cell(cell.row, 2).value)
                    return {
                        'type': 'referral_invite',
                        'discount': 20,
                        'owner_id': owner_id,
                        'row_index': cell.row,
                        'status': status  # <--- Теперь статус всегда будет в словаре
                    }
        except Exception as e:
            print(f"Ошибка при поиске реферального кода {promo_code}: {e}")
        # Если не нашли или статус не 'generated', возвращаем None
        return None

    # --- НОВЫЙ СЦЕНАРИЙ 2: Наградной код за друга ---
    elif promo_code.startswith("REWARD-"):
        try:
            worksheet = spreadsheet.worksheet(WORKSHEET_REFERRALS)
            # Ищем наградной код в 6-м столбце
            cell = worksheet.find(promo_code, in_column=6)
            if cell:
                # Проверяем, что основной код уже использован (доп. защита)
                status = worksheet.cell(cell.row, 5).value
                if status == 'used':
                     return {'type': 'referral_reward', 'discount': 20, 'status': 'active'}
        except Exception as e:
            print(f"Ошибка при поиске наградного кода {promo_code}: {e}")
        return None

    # СЦЕНАРИЙ 3: Это любой другой (стандартный или наградной) промокод
    else:
        try:
            worksheet = spreadsheet.worksheet(WORKSHEET_PROMOCODES)
            cell = worksheet.find(promo_code, in_column=1)
            if cell:
                discount = int(worksheet.cell(cell.row, 2).value)
                return {
                    'type': 'standard',  # или 'referral_reward', если у вас есть такая логика
                    'discount': discount,
                    'status': 'active'  # <--- Для стандартных кодов будем считать, что они всегда активны
                }
        except Exception as e:
            print(f"Ошибка при поиске стандартного промокода {promo_code}: {e}")

    return None  # Если нигде не нашли

async def generate_and_add_referral_code(user_id: int) -> str | None:
    """Генерирует уникальный реферальный код и добавляет его в лист 'Referrals'."""
    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_REFERRALS)
        code = "FRIEND-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

        while worksheet.find(code, in_column=1):
            code = "FRIEND-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

        # InviteCode, OwnerUserID, FriendUserID, FriendOrderID, Status, RewardCode
        row_data = [code, user_id, '', '', 'generated', '']
        worksheet.append_row(row_data)
        return code
    except Exception as e:
        print(f"Ошибка при генерации реферального кода для {user_id}: {e}")
        return None
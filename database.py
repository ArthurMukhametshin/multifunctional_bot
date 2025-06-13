import aiosqlite
from datetime import datetime

DB_NAME = 'bot_database.db'


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                phone_number TEXT,
                registration_date TEXT,
                loyalty_visits INTEGER NOT NULL DEFAULT 0
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_id INTEGER,
                payment_id TEXT,
                status TEXT DEFAULT 'pending', -- pending, paid, cancelled
                amount INTEGER,
                promo_code TEXT,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        # Обратите внимание, что мы убрали event_id из FOREIGN KEY для orders,
        # так как таблицы events больше нет. Если у вас это осталось, удалите.
        # В вашем коде этого, скорее всего, нет, но на всякий случай проверьте.

        await db.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_id INTEGER,
                feedback_text TEXT,
                created_at TEXT
            )
        ''')
        await db.commit()

# --- Функции для работы с пользователями ---
async def add_user(user_id, username):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if await cursor.fetchone() is None:
            await db.execute(
                "INSERT INTO users (user_id, username, registration_date) VALUES (?, ?, ?)",
                (user_id, username, datetime.now().isoformat())
            )
            await db.commit()

async def update_user_contacts(user_id, full_name, phone_number):
     async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET full_name = ?, phone_number = ? WHERE user_id = ?",
            (full_name, phone_number, user_id)
        )
        await db.commit()

# --- Функции для работы с мероприятиями и заказами ---
async def create_order(user_id, event_id, amount):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO orders (user_id, event_id, amount, created_at) VALUES (?, ?, ?, ?)",
            (user_id, event_id, amount, datetime.now().isoformat())
        )
        await db.commit()
        cursor = await db.execute("SELECT last_insert_rowid()")
        return (await cursor.fetchone())[0]

async def update_order_status(order_id, payment_id, status):
     async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE orders SET status = ?, payment_id = ? WHERE id = ?",
            (status, payment_id, order_id)
        )
        await db.commit()

async def get_loyalty_count(user_id: int) -> int:
    """Получает текущее количество накопленных визитов для лояльности."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT loyalty_visits FROM users WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 0

async def increment_loyalty_count(user_id: int):
    """Увеличивает счетчик лояльности на 1."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET loyalty_visits = loyalty_visits + 1 WHERE user_id = ?", (user_id,))
        await db.commit()

async def reset_loyalty_count(user_id: int):
    """Сбрасывает счетчик лояльности до 0."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET loyalty_visits = 0 WHERE user_id = ?", (user_id,))
        await db.commit()

async def get_user_paid_orders(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM orders WHERE user_id = ? AND status = 'paid'", (user_id,))
        return await cursor.fetchall()

async def get_order_by_id(order_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        return await cursor.fetchone()

async def decrement_loyalty_count(user_id: int):
    """Уменьшает счетчик лояльности на 1, но не ниже нуля."""
    async with aiosqlite.connect(DB_NAME) as db:
        # Добавляем проверку, чтобы счетчик не ушел в минус
        await db.execute(
            "UPDATE users SET loyalty_visits = loyalty_visits - 1 WHERE user_id = ? AND loyalty_visits > 0",
            (user_id,)
        )
        await db.commit()

async def check_if_ticket_exists(user_id: int, event_id: int) -> bool:
    """
    Проверяет, есть ли у пользователя уже купленный (статус 'paid')
    билет на это мероприятие.
    Возвращает True, если билет есть, иначе False.
    """
    async with aiosqlite.connect(DB_NAME) as db:
        # Мы ищем хотя бы одну запись, LIMIT 1 делает запрос быстрее
        cursor = await db.execute(
            "SELECT 1 FROM orders WHERE user_id = ? AND event_id = ? AND status = 'paid' LIMIT 1",
            (user_id, event_id)
        )
        # Если fetchone() вернет что-то (кортеж), значит запись есть. Если None - записи нет.
        return await cursor.fetchone() is not None

async def set_loyalty_points(user_id: int, points: int):
    """Устанавливает точное количество баллов лояльности."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET loyalty_visits = ? WHERE user_id = ?", (points, user_id))
        await db.commit()

async def update_order_payment_id(order_id: int, payment_id: str):
    """Обновляет payment_id для заказа."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE orders SET payment_id = ? WHERE id = ?", (payment_id, order_id))
        await db.commit()

async def get_user_by_id(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return await cursor.fetchone()
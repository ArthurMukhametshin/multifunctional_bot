import asyncio
import logging
from handlers import feedback_handlers
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config_reader import config
from handlers import user_handlers, booking_handlers
from database import init_db
from utils.scheduler import send_arrival_info

# --- Глобальный объект шедулера ---
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

async def main():
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=config.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

    await init_db()

    dp.include_router(user_handlers.router)
    dp.include_router(booking_handlers.router)
    dp.include_router(feedback_handlers.router)

    scheduler.start()

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен")
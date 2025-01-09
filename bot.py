import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from handlers import registration, projects
from middlewares.registration_middleware import RegistrationMiddleware
from config import BOT_TOKEN, DATABASE_URL
from data.models import create_db_session

logging.basicConfig(level=logging.INFO)

storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

dp.include_router(registration.router)
dp.include_router(projects.router)

dp.message.middleware(RegistrationMiddleware())

async def main():
    # Создаем сессию для инициализации базы данных
    session = create_db_session(DATABASE_URL)
    session.close()
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
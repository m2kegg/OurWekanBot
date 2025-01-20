import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from handlers import registration, projects
from middlewares.checkup_middleware import OnlyCommandMiddleware
from middlewares.logging_middleware import DatabaseLoggingMiddleware
from middlewares.registration_middleware import RegistrationMiddleware
from config import BOT_TOKEN, DATABASE_URL, DATABASE_LOG_URL
from data.models import create_db_session

logging.basicConfig(level=logging.INFO)

disabled_states_list = [
    "CreateProjectForm:waiting_for_project_name",
    "CreateProjectForm:waiting_for_project_description",
    "JoinProjectForm:waiting_for_project_key",
    "CreateTaskForm:waiting_for_task_name",
    "CreateTaskForm:waiting_for_task_description",
    "CreateTaskForm:waiting_for_task_users",
    "CreateTaskForm:waiting_for_task_deadline",
    "CreateTaskForm:waiting_for_task_hours",
    "CreateTaskForm:waiting_for_task_confirm",
    "EditTaskStatusForm:waiting_for_new_status",
]

storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

dp.include_router(registration.router)
dp.include_router(projects.router)

dp.message.middleware(RegistrationMiddleware())
dp.message.middleware(DatabaseLoggingMiddleware(DATABASE_LOG_URL))
dp.message.middleware(OnlyCommandMiddleware(disabled_states_list))

async def main():
    # Создаем сессию для инициализации базы данных
    session = create_db_session(DATABASE_URL)
    session.close()
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from data.models import User, create_db_session
from config import DATABASE_URL
from handlers.registration import RegistrationForm

class RegistrationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        session = create_db_session(DATABASE_URL)
        user = session.query(User).filter(User.user_id == user_id).first()
        session.close()
        logging.info(f"Handling middleware for user ID: {user_id}")
        if not user:
            logging.info(f"User not found")
            state: FSMContext = data["state"]
            current_state = await state.get_state()
            if current_state is None:
                await event.answer("Привет! Кажется, ты еще не зарегистрирован. Пожалуйста, введи свое ФИО.")
                await state.set_state(RegistrationForm.waiting_for_fullname)
                return

        return await handler(event, data)
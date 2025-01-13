import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        user_username = event.from_user.username
        user_fullname = event.from_user.full_name

        if isinstance(event, Message):
            action_type = "message"
            content = event.text
        elif isinstance(event, CallbackQuery):
            action_type = "callback_query"
            content = event.data
        else:
            action_type = "unknown"
            content = None

        logging.info(f"User ID: {user_id}, Username: {user_username}, Fullname: {user_fullname}, Action Type: {action_type}, Content: {content}")
        return await handler(event, data)
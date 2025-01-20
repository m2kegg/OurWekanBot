from typing import Callable, Any, Awaitable, List

from aiogram import BaseMiddleware, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton

ALLOWED_COMMANDS = ["Мои проекты", "Создать проект", "Присоединиться к проекту"]

class OnlyCommandMiddleware(BaseMiddleware):
    def __init__(self, disabled_states: List[str] = None):
        self.disabled_states = disabled_states or []

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any]
    ) -> Any:
        bot = data["bot"]
        state: FSMContext = data.get('state')
        user_id = event.from_user.id

        if state:
            current_state = await state.get_state()
            print(current_state)
            print(self.disabled_states)
            if current_state in self.disabled_states:
                return await handler(event, data)

        if isinstance(event, Message):
            if event.text:
                if event.text.startswith("/") or event.text in ALLOWED_COMMANDS:
                    return await handler(event, data)

                if event.reply_markup and isinstance(event.reply_markup, ReplyKeyboardMarkup):
                    for row in event.reply_markup.keyboard:
                        for button in row:
                            if button.text == event.text:
                                return await handler(event, data)
                    await bot.delete_message(chat_id=user_id, message_id=event.message_id)
                    return

                if not event.reply_markup:
                    await bot.delete_message(chat_id=user_id, message_id=event.message_id)
                    return

        elif isinstance(event, CallbackQuery):
            return await handler(event, data)

        return
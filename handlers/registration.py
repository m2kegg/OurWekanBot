import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from config import DATABASE_URL
from data.models import User, create_db_session

router = Router()

class RegistrationForm(StatesGroup):
    waiting_for_fullname = State()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logging.info(f"Handling /start for user ID: {user_id}")
    session = create_db_session(DATABASE_URL)
    user = session.query(User).filter(User.user_id == user_id).first()
    session.close()
    if not user:
        await message.answer("Привет! Пожалуйста, введи свое ФИО.")
        await state.set_state(RegistrationForm.waiting_for_fullname)
    else:
        await show_main_menu(message)

@router.message(RegistrationForm.waiting_for_fullname)
async def process_fullname(message: Message, state: FSMContext):
    fullname = message.text
    user_id = message.from_user.id
    session = create_db_session(DATABASE_URL)
    user = User(user_id=user_id, fullname=fullname)
    session.add(user)
    session.commit()
    session.close()
    await state.clear()
    await message.answer(f"Отлично, {fullname}! Теперь ты можешь пользоваться ботом.")
    await show_main_menu(message)

async def show_main_menu(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Мои проекты")],
            [KeyboardButton(text="Создать проект")],
            [KeyboardButton(text="Присоединиться к проекту")],
        ],
        resize_keyboard=True
    )
    await message.answer("Главное меню:", reply_markup=keyboard)
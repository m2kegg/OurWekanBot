import uuid

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from config import BASE_URL, DATABASE_URL
from data.models import Project, UserProjectAssociation, create_db_session, User

router = Router()

PROJECTS_PER_PAGE = 5
MEMBERS_PER_PAGE = 5


class CreateProjectForm(StatesGroup):
    waiting_for_project_name = State()


class JoinProjectForm(StatesGroup):
    waiting_for_project_key = State()


def generate_unique_project_key():
    return uuid.uuid4().hex[:8]


@router.message(F.text == "Мои проекты")
async def show_user_projects_paged(message: Message, state: FSMContext, page: int = 1):
    user_id = message.from_user.id
    session = create_db_session(DATABASE_URL)
    user_projects = session.query(Project).join(UserProjectAssociation).filter(
        UserProjectAssociation.user_id == user_id).all()
    session.close()

    if not user_projects:
        await message.answer("Ты пока не участвуешь ни в одном проекте.")
        return

    total_projects = len(user_projects)
    start_index = (page - 1) * PROJECTS_PER_PAGE
    end_index = start_index + PROJECTS_PER_PAGE
    projects_on_page = user_projects[start_index:end_index]
    total_pages = (total_projects + PROJECTS_PER_PAGE - 1) // PROJECTS_PER_PAGE

    keyboard_buttons = []
    for project in projects_on_page:
        keyboard_buttons.append(
            [InlineKeyboardButton(text=project.name, callback_data=f"view_project:{project.project_id}")])

    navigation_buttons = []
    if page > 1:
        navigation_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"projects_page:{page - 1}"))
    if page < total_pages:
        navigation_buttons.append(InlineKeyboardButton(text="➡️ Вперед", callback_data=f"projects_page:{page + 1}"))

    if navigation_buttons:
        keyboard_buttons.append(navigation_buttons)

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer("Твои проекты:", reply_markup=markup)


@router.callback_query(F.data.startswith("projects_page:"))
async def paginate_projects(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[1])
    await show_user_projects_paged(callback.message, state, page)
    await callback.answer()


@router.callback_query(F.data.startswith("view_project:"))
async def view_project_details(callback: CallbackQuery, state: FSMContext, page: int = 1):
    project_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    session = create_db_session(DATABASE_URL)
    project = session.query(Project).get(project_id)
    user_association = session.query(UserProjectAssociation).filter(UserProjectAssociation.user_id == user_id,
                                                                    UserProjectAssociation.project_id == project_id).first()

    if not project or not user_association:
        await callback.answer("Проект не найден или у вас нет доступа.", show_alert=True)
        session.close()
        return

    keyboard_buttons = []
    if user_association.role == "Администратор":
        members = session.query(User).join(UserProjectAssociation).filter(
            UserProjectAssociation.project_id == project_id).all()
        total_members = len(members)
        start_index = (page - 1) * MEMBERS_PER_PAGE
        end_index = start_index + MEMBERS_PER_PAGE
        members_on_page = members[start_index:end_index]
        total_pages = (total_members + MEMBERS_PER_PAGE - 1) // MEMBERS_PER_PAGE

        for member in members_on_page:
            keyboard_buttons.append([InlineKeyboardButton(text=member.fullname,
                                                          callback_data=f"view_member_roles:{project_id}:{member.user_id}")])

        navigation_buttons = []
        if page > 1:
            navigation_buttons.append(
                InlineKeyboardButton(text="⬅️ Назад", callback_data=f"members_page:{project_id}:{page - 1}"))
        if page < total_pages:
            navigation_buttons.append(
                InlineKeyboardButton(text="➡️ Вперед", callback_data=f"members_page:{project_id}:{page + 1}"))

        if navigation_buttons:
            keyboard_buttons.append(navigation_buttons)

        keyboard_buttons.append(
            [InlineKeyboardButton(text="Редактировать роли", callback_data=f"edit_roles:{project_id}")])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(f"Проект: {project.name}", reply_markup=markup)
    await callback.answer()
    session.close()

@router.callback_query(F.data.startswith("members_page:"))
async def paginate_members(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    project_id = int(parts[1])
    page = int(parts[2])
    await view_project_details(callback, state, page)
    await callback.answer()

@router.callback_query(F.data.startswith("edit_roles:"))
async def edit_project_roles(callback: CallbackQuery, state: FSMContext):
    project_id = int(callback.data.split(":")[1])
    session = create_db_session(DATABASE_URL)
    members = session.query(User).join(UserProjectAssociation).filter(UserProjectAssociation.project_id == project_id).all()
    keyboard_buttons = []
    for member in members:
        keyboard_buttons.append([InlineKeyboardButton(text=member.fullname, callback_data=f"set_role:{project_id}:{member.user_id}")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text("Выберите пользователя для изменения роли:", reply_markup=markup)
    await callback.answer()
    session.close()

@router.callback_query(F.data.startswith("set_role:"))
async def show_role_options(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    project_id = int(parts[1])
    member_id = int(parts[2])
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сделать администратором", callback_data=f"change_role:{project_id}:{member_id}:Администратор")],
        [InlineKeyboardButton(text="Сделать участником", callback_data=f"change_role:{project_id}:{member_id}:Участник")],
    ])
    await callback.message.edit_text("Выберите роль:", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("change_role:"))
async def change_user_role(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    project_id = int(parts[1])
    member_id = int(parts[2])
    new_role = parts[3]
    session = create_db_session(DATABASE_URL)
    association = session.query(UserProjectAssociation).filter(UserProjectAssociation.project_id == project_id, UserProjectAssociation.user_id == member_id).first()
    if association:
        old_role = association.role
        association.role = new_role
        session.commit()
        member = session.query(User).get(member_id)
        await callback.message.edit_text(f"Роль пользователя {member.fullname} изменена на '{new_role}'.")
        # Отправка уведомления пользователю (опционально)
        await callback.bot.send_message(member_id, f"Ваша роль в проекте '{association.project.name}' изменена на '{new_role}'.")
    else:
        await callback.answer("Запись о членстве не найдена.", show_alert=True)
    session.close()
    await callback.answer()

@router.callback_query(F.data.startswith("cancel_project"))
async def change_user_role(callback: CallbackQuery, state: FSMContext):
    if(state == CreateProjectForm.waiting_for_project_name):
        await callback.message.answer("Создание проекта отменено", reply_markup=get_main_keyboard())
        await state.clear()
    return

@router.message(F.text == "Создать проект")
async def create_project(message: Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data="cancel_project")]
              ],
        resize_keyboard=True
    )
    await message.answer("Как назовем проект?", reply_markup=keyboard)
    
    await state.set_state(CreateProjectForm.waiting_for_project_name)


@router.message(CreateProjectForm.waiting_for_project_name)
async def process_project_name(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await message.answer("Создание проекта отменено", reply_markup=get_main_keyboard())
        await state.clear()
        return
    project_name = message.text
    user_id = message.from_user.id
    session = create_db_session(DATABASE_URL)
    project_key = generate_unique_project_key()
    project = Project(name=project_name, owner_id=user_id, project_key=project_key)
    session.add(project)
    session.flush()
    user_project_association = UserProjectAssociation(user_id=user_id, project_id=project.project_id,
                                                      role="Администратор")
    session.add(user_project_association)
    session.commit()
    session.close()
    await message.answer(f"Проект '{project_name}' создан! Ты являешься администратором.")
    await message.answer(f"Ключ для присоединения к проекту: `{project_key}`", parse_mode="Markdown")
    await state.clear()


@router.message(F.text=="Присоединиться к проекту")
async def join_project_command(message: Message, state: FSMContext):
    await message.answer("Введите ключ проекта:")
    await state.set_state(JoinProjectForm.waiting_for_project_key)

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Мои проекты")],
            [KeyboardButton(text="Создать проект")],
            [KeyboardButton(text="Присоединиться к проекту")],
        ],
        resize_keyboard=True
    )


@router.message(JoinProjectForm.waiting_for_project_key)
async def process_project_key(message: Message, state: FSMContext):
    project_key = message.text.strip()
    user_id = message.from_user.id
    session = create_db_session(DATABASE_URL)
    project = session.query(Project).filter(Project.project_key == project_key).first()

    if project:
        # Проверяем, не состоит ли пользователь уже в проекте
        existing_membership = session.query(UserProjectAssociation).filter(
            UserProjectAssociation.user_id == user_id,
            UserProjectAssociation.project_id == project.project_id
        ).first()
        if not existing_membership:
            user_project_association = UserProjectAssociation(user_id=user_id, project_id=project.project_id,
                                                              role="Участник")
            session.add(user_project_association)
            session.commit()
            await message.answer(f"Ты успешно присоединился к проекту '{project.name}'.")
        else:
            await message.answer("Ты уже состоишь в этом проекте.")
    else:
        await message.answer("Неверный ключ проекта.")

    session.close()
    await state.clear()


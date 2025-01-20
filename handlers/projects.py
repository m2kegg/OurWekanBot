import logging
import uuid
from datetime import datetime, timedelta

import apscheduler.schedulers.background
from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, \
    KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback

from config import BASE_URL, DATABASE_URL
from data.models import Project, UserProjectAssociation, create_db_session, User, Task, TaskEnum, \
    TaskProjectAssociation, UserTaskAssociation
from data.models import Project, UserProjectAssociation, create_db_session, User
from aiogram.methods import edit_message_text

from apscheduler.triggers.date import DateTrigger

from handlers.registration import show_main_menu
from llm.gigachat import analyze_employee, get_task_advice

router = Router()

scheduler = apscheduler.schedulers.background.BackgroundScheduler()
scheduler.start()

PROJECTS_PER_PAGE = 4
MEMBERS_PER_PAGE = 4
TASKS_PER_PAGE = 4



class CreateProjectForm(StatesGroup):
    waiting_for_project_name = State()
    waiting_for_project_description = State()


class JoinProjectForm(StatesGroup):
    waiting_for_project_key = State()

class CreateTaskForm(StatesGroup):
    waiting_for_task_name = State()
    waiting_for_task_description = State()
    waiting_for_task_users = State()
    waiting_for_task_deadline = State()
    waiting_for_task_hours = State()
    waiting_for_task_confirm = State()

class EditTaskStatusForm(StatesGroup):
    waiting_for_new_status = State()



def generate_unique_project_key():
    return uuid.uuid4().hex[:8]

router = Router()

@router.message(F.text == "Мои проекты")
async def show_user_projects_paged(message: Message, state: FSMContext, page: int = 1, callback_query: CallbackQuery = None):
    user_id = message.from_user.id if callback_query is None else callback_query.from_user.id

    session = create_db_session(DATABASE_URL)
    await state.clear()
    user_projects = session.query(Project).join(UserProjectAssociation).filter(
        UserProjectAssociation.user_id == user_id).all()
    session.close()

    if not user_projects:
        if callback_query:
            await callback_query.message.edit_text("Ты пока не участвуешь ни в одном проекте.")
        else:
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

    keyboard_buttons.append([InlineKeyboardButton(text="❌Отмена❌", callback_data=f"cancel_project_view")])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    if callback_query:
        await callback_query.message.edit_text("Твои проекты:", reply_markup=markup)
    else:
        await message.answer("Твои проекты:", reply_markup=markup)


@router.callback_query(F.data.startswith("projects_page:"))
async def paginate_projects(callback: CallbackQuery, bot: Bot, state: FSMContext):
    page = int(callback.data.split(":")[1])
    await show_user_projects_paged(callback.message, state, page, callback_query=callback)
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
                                                          callback_data=f"analyze_member:{project_id}:{member.user_id}")])

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
            [InlineKeyboardButton(text="Редактировать роли", callback_data=f"edit_roles:{project_id}"),
             InlineKeyboardButton(text="Просмотреть задачи", callback_data=f"view_tasks:{project_id}"),
             InlineKeyboardButton(text="Добавить задачу", callback_data=f"create_task:{project_id}"),])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(f"Проект: {project.name}", reply_markup=markup)
    await callback.answer()
    session.close()

@router.callback_query(F.data.startswith("view_tasks:"))
async def show_project_tasks_paged(callback: CallbackQuery, state: FSMContext, page: int = 1):
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

    tasks = session.query(Task).join(TaskProjectAssociation).filter(TaskProjectAssociation.project_id == project_id).all()
    session.close()

    if not tasks:
        await callback.message.edit_text("В этом проекте пока нет задач.")
        return

    total_tasks = len(tasks)
    start_index = (page - 1) * TASKS_PER_PAGE
    end_index = start_index + TASKS_PER_PAGE
    tasks_on_page = tasks[start_index:end_index]
    total_pages = (total_tasks + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE

    keyboard_buttons = []
    for task in tasks_on_page:
        keyboard_buttons.append([InlineKeyboardButton(text=task.name, callback_data=f"view_task_details:{task.task_id}")])

    navigation_buttons = []
    if page > 1:
        navigation_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"tasks_page:{project_id}:{page - 1}"))
    if page < total_pages:
        navigation_buttons.append(InlineKeyboardButton(text="➡️ Вперед", callback_data=f"tasks_page:{project_id}:{page + 1}"))

    if navigation_buttons:
        keyboard_buttons.append(navigation_buttons)

    keyboard_buttons.append([InlineKeyboardButton(text="Назад к проекту", callback_data=f"view_project:{project_id}")])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(f"Задачи проекта '{project.name}':", reply_markup=markup)
    await callback.answer()

@router.callback_query(F.data.startswith("tasks_page:"))
async def paginate_tasks(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    project_id = int(parts[1])
    page = int(parts[2])
    await show_project_tasks_paged(callback, state, page)
    await callback.answer()

@router.callback_query(F.data.startswith("view_task_details:"))
async def view_task_details(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    session = create_db_session(DATABASE_URL)
    task = session.query(Task).get(task_id)
    project = session.query(Project).join(TaskProjectAssociation).filter(TaskProjectAssociation.task_id == task_id).first()
    user_association = session.query(UserProjectAssociation).filter(
        UserProjectAssociation.user_id == user_id,
        UserProjectAssociation.project_id == project.project_id
    ).first()
    session.close()

    if not task:
        await callback.answer("Задача не найдена.", show_alert=True)
        return

    message_text = f"Задача: {task.name}\n" \
                   f"Описание: {task.description}\n" \
                   f"Статус: {task.State.value}\n" \
                   f"Дедлайн: {task.deadline_date.strftime('%d.%m.%Y')}"

    keyboard_buttons = []
    if user_association and user_association.role == "Администратор":
        keyboard_buttons.append([InlineKeyboardButton(text="Изменить статус", callback_data=f"edit_task_status:{task_id}")])
    keyboard_buttons.append([InlineKeyboardButton(text="Назад к задачам", callback_data=f"view_tasks:{project.project_id}")])
    keyboard_buttons.append([InlineKeyboardButton(text="Проанализировать задачу", callback_data=f"analyze_task:{task_id}")])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(message_text, reply_markup=markup)
    await callback.answer()

@router.callback_query(F.data.startswith("analyze_task:"))
async def analyze_task_callback(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split(":")[1])
    advice = get_task_advice(task_id)
    keyboard = []
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"view_task_details:{task_id}")])
    await callback.message.edit_text(text=advice, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

@router.callback_query(F.data.startswith("edit_task_status:"))
async def edit_task_status(callback: CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split(":")[1])
    await state.update_data(task_id=task_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=TaskEnum.IN_WORK.value, callback_data=f"set_task_status:{task_id}:{TaskEnum.IN_WORK.value}")],
        [InlineKeyboardButton(text=TaskEnum.ON_REVISION.value, callback_data=f"set_task_status:{task_id}:{TaskEnum.ON_REVISION.value}")],
        [InlineKeyboardButton(text=TaskEnum.DONE.value, callback_data=f"set_task_status:{task_id}:{TaskEnum.DONE.value}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_task_details:{task_id}")],
    ])
    await callback.message.edit_text("Выберите новый статус задачи:", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("set_task_status:"))
async def set_task_status(callback: CallbackQuery, state: FSMContext):
    _, task_id, new_status_str = callback.data.split(":")
    task_id = int(task_id)
    try:
        new_status = TaskEnum(new_status_str)
        session = create_db_session(DATABASE_URL)
        task = session.query(Task).get(task_id)
        if task:
            task.State = new_status
            session.commit()
            await callback.message.edit_text(f"Статус задачи '{task.name}' изменен на '{new_status.value}'.")
        else:
            await callback.answer("Задача не найдена.", show_alert=True)
        session.close()
    except ValueError:
        await callback.answer("Неверный статус задачи.", show_alert=True)
    await callback.answer()
@router.callback_query(F.data.startswith("analyze_member:"))
async def analyze_member_handler(callback: CallbackQuery, state: FSMContext):
    _, project_id, member_id = callback.data.split(":")
    project_id = int(project_id)
    member_id = int(member_id)
    try:
        analysis_result = analyze_employee(member_id, project_id)
        await callback.message.answer(f"Анализ производительности сотрудника:\n{analysis_result}")
    except Exception as e:
        logging.error(f"Ошибка при анализе сотрудника: {e}")
        await callback.message.answer("Произошла ошибка при анализе производительности сотрудника.")
    await callback.answer()

@router.callback_query(F.data.startswith("members_page:"))
async def paginate_members(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    project_id = int(parts[1])
    page = int(parts[2])
    await view_project_details(callback, state, page)
    await callback.answer()

@router.callback_query(F.data.startswith("create_task:"))
async def create_task(callback: CallbackQuery, state: FSMContext, bot:Bot):
    parts = callback.data.split(":")
    project_id = int(parts[1])
    await state.update_data(project_id=project_id)
    await bot.send_message(text="""Сейчас будет вызвана процедура создания задачи для проекта.
    Необходимо указать:
    1) Название задачи, 
    2) Описание (что нужно будет выполнить в рамках этой задачи) 
    3) Количество часов, которое зачтётся при выполнении этой задачи
    4) Дедлайн выполнения данной задачи.
    
    Начнём с названия. Как будет называться задача?""",chat_id=callback.from_user.id, reply_markup=ReplyKeyboardRemove())
    await state.set_state(CreateTaskForm.waiting_for_task_name)

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


@router.message(CreateTaskForm.waiting_for_task_name)
async def create_task_name(message: Message, state: FSMContext):
    task_name = message.text
    await state.update_data(task_name=task_name)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_project")],
            [InlineKeyboardButton(text="⬅️ Назад к выбору названия", callback_data="back_to_name")]
        ],
        resize_keyboard=True
    )
    await message.answer(f"Название твоей задачи - {task_name}.")
    await message.answer(f"Переходим к созданию описания задачи. Необходимо четко сформулировать, что требуется в этой задаче.", reply_markup=keyboard)
    await state.set_state(CreateTaskForm.waiting_for_task_description)

@router.message(CreateTaskForm.waiting_for_task_description)
async def create_task_description(message: Message, state: FSMContext, page: int = 1):

    task_description = message.text
    await state.update_data(task_description=task_description)
    await state.update_data(selected_members=[])
    await show_member_selection_keyboard(message, state,)

async def show_member_selection_keyboard(message: Message, state: FSMContext, page: int = 1):
    data = await state.get_data()
    project_id = int(data.get("project_id"))
    session = create_db_session(DATABASE_URL)
    members = session.query(User).join(UserProjectAssociation).filter(
        UserProjectAssociation.project_id == project_id).all()
    session.close()
    total_members = len(members)
    start_index = (page - 1) * MEMBERS_PER_PAGE
    end_index = start_index + MEMBERS_PER_PAGE
    members_on_page = members[start_index:end_index]
    total_pages = (total_members + MEMBERS_PER_PAGE - 1) // MEMBERS_PER_PAGE
    selected_members_data = await state.get_data()
    selected_members = selected_members_data.get("selected_members", [])

    keyboard_buttons = []
    for member in members_on_page:
        checkmark = "✅" if member.user_id in selected_members else ""
        keyboard_buttons.append([InlineKeyboardButton(text=f"{member.fullname} {checkmark}",
                                                      callback_data=f"check_member:{project_id}:{member.user_id}")])

    pagination_buttons = []
    if page > 1:
        pagination_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"members_task_page:{page - 1}"))
    if page < total_pages:
        pagination_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"members_task_page:{page + 1}"))

    keyboard_buttons.append(pagination_buttons)
    keyboard_buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_task")])
    keyboard_buttons.append([InlineKeyboardButton(text="⬅️ Назад к описанию", callback_data="back_to_task_desc")])
    keyboard_buttons.append([InlineKeyboardButton(text="✅ Подтвердить выбор", callback_data="confirm_assignees")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons, resize_keyboard=True)
    await message.answer("Выбери исполнителей для задачи:", reply_markup=keyboard)
    await state.set_state(CreateTaskForm.waiting_for_task_users)

@router.callback_query(CreateTaskForm.waiting_for_task_users, F.data.startswith("check_member:"))
async def check_member(callback: CallbackQuery, state: FSMContext):
    _, project_id, user_id = callback.data.split(":")
    user_id = int(user_id)
    selected_members_data = await state.get_data()
    selected_members = selected_members_data.get("selected_members", [])

    if user_id in selected_members:
        selected_members.remove(user_id)
    else:
        selected_members.append(user_id)

    await state.update_data(selected_members=selected_members)
    current_page_data = await state.get_data()
    await show_member_selection_keyboard(callback.message, state, current_page_data.get('current_members_page', 1))
    await callback.answer()

@router.callback_query(CreateTaskForm.waiting_for_task_users, F.data.startswith("members_task_page:"))
async def navigate_members_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[1])
    await state.update_data(current_members_page=page)
    await show_member_selection_keyboard(callback.message, state, page)
    await callback.answer()

@router.callback_query(CreateTaskForm.waiting_for_task_description, F.data == "back_to_task_desc")
async def back_to_task_desc(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CreateTaskForm.waiting_for_task_description)
    await callback.message.answer("Возвращаемся к редактированию описания задачи.")
    await callback.answer()

@router.callback_query(F.data == "cancel_task")
async def cancel_project(callback: CallbackQuery, state: FSMContext, bot:Bot):
    await state.clear()
    await callback.message.answer("Создание задачи отменено.")
    await bot.send_message(text = "Главное меню:", chat_id=callback.from_user.id, reply_markup=get_main_keyboard())
    await callback.answer()

@router.callback_query(CreateTaskForm.waiting_for_task_users, F.data == "confirm_assignees")
async def confirm_assignees(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_members = data.get("selected_members", [])
    if selected_members:
        session = create_db_session(DATABASE_URL)
        assignees = session.query(User).filter(User.user_id.in_(selected_members)).all()
        session.close()
        assignee_names = [user.fullname for user in assignees]
        await callback.message.answer(f"Вы выбрали следующих исполнителей: {', '.join(assignee_names)}")
        await callback.message.answer("Теперь, пожалуйста, напишите количество часов. которое будет зачтено при выполнении данной задачи:")
        await state.set_state(CreateTaskForm.waiting_for_task_hours)
    else:
        await callback.message.answer("Вы не выбрали ни одного исполнителя.", show_alert=True)
    await callback.answer()

@router.callback_query(CreateTaskForm.waiting_for_task_hours)
async def process_hours(callback: CallbackQuery, state: FSMContext):
    hours = callback.message.text
    if hours.isnumeric():
        hours = int(hours)
        await state.update_data(hours=hours)
        await callback.message.answer("Теперь, пожалуйста, выберите дату дедлайна:",
                                      reply_markup=await SimpleCalendar().start_calendar())
        await state.set_state(CreateTaskForm.waiting_for_task_hours)
    else:
        await callback.message.answer("Просьба ввести часы в целом десятичном виде", show_alert=True)


@router.callback_query(CreateTaskForm.waiting_for_task_deadline, SimpleCalendarCallback.filter())
async def process_deadline_selection(callback: CallbackQuery, state: FSMContext, callback_data: dict):
    selected, date = await SimpleCalendar().process_selection(callback, callback_data)
    if selected:
        today = datetime.now().today()
        if date <= today:
            await callback.answer("Дата дедлайна должна быть позже сегодняшнего дня.", show_alert=True)
            await callback.message.edit_text(
                "Пожалуйста, выберите корректную дату дедлайна:",
                reply_markup=await SimpleCalendar().start_calendar()
            )
            return

        await state.update_data(deadline_date=date)
        data = await state.get_data()
        selected_members = data.get("selected_members", [])
        session = create_db_session(DATABASE_URL)
        assignees = session.query(User).filter(User.user_id.in_(selected_members)).all()
        session.close()
        assignee_names = [user.fullname for user in assignees]
        task_name = data.get("task_name")
        task_description = data.get("task_description")
        hours = data.get("hours")
        await callback.message.edit_text(
            f"""Вы выбрали дедлайн: {date.strftime('%d.%m.%Y')}
            Итак, Ваша введённая задача выглядит следующим образом:

            Название задачи: {task_name}
            Описание задачи: {task_description}
            Команда, назначенная на выполнение задачи: {assignee_names}
            Количество часов: {hours}
            Дедлайн: {date.strftime('%d.%m.%Y')}""",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Подтвердить задачу", callback_data="confirm_task_creation")],
                    [InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_task")]
                ]
            ),
        )
        await callback.answer()




@router.callback_query(F.data == "confirm_task_creation")
async def confirm_task_creation(callback: CallbackQuery, state: FSMContext, bot:Bot):
    data = await state.get_data()
    task_name = data.get("task_name")
    task_description = data.get("task_description")
    selected_members = data.get("selected_members")
    deadline_date = data.get("deadline_date")
    project_id = data.get("project_id")

    if all([task_name, task_description, selected_members, deadline_date, project_id]):
        session = create_db_session(DATABASE_URL)
        new_task = Task(
            name=task_name,
            description=task_description,
            start_date=datetime.now().date(),
            deadline_date=deadline_date,
            time_taken=0,
            State=TaskEnum.IN_WORK
        )
        
        session.add(new_task)
        session.flush()

        task_project_association = TaskProjectAssociation(task_id=new_task.task_id, project_id=project_id)
        session.add(task_project_association)

        for user_id in selected_members:
            user_task_association = UserTaskAssociation(user_id=user_id, task_id=new_task.task_id)
            session.add(user_task_association)

        session.commit()
        task_id = new_task.task_id
        session.close()
        schedule_deadline_notification(task_id, deadline_date, bot)
        await callback.message.answer("Задача успешно создана!")
     
        await bot.send_message(text = "Главное меню:", chat_id=callback.from_user.id, reply_markup=get_main_keyboard())
        await state.clear()
    else:
        await callback.message.answer("Недостаточно данных для создания задачи. Пожалуйста, попробуйте еще раз.")
        await bot.send_message(text = "Главное меню:", chat_id=callback.from_user.id, reply_markup=get_main_keyboard())
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

@router.callback_query(F.data.startswith("cancel_project_naming"))
async def cancel_project_naming(callback: CallbackQuery, state: FSMContext, bot:Bot):
    
    await callback.message.edit_text("Создание проекта отменено")
   
    await state.clear()
    await bot.send_message(text = "Главное меню:", chat_id=callback.from_user.id, reply_markup=get_main_keyboard())
    await callback.answer()

@router.callback_query(F.data.startswith("cancel_project_view"))
async def cancel_project_view(callback: CallbackQuery, state: FSMContext, bot:Bot):
    await state.clear()
    await callback.message.edit_text("Просмотр проектов завершен.")
    await bot.send_message(text = "Главное меню:", chat_id=callback.from_user.id, reply_markup=get_main_keyboard())
    await callback.answer()

@router.callback_query(F.data.startswith("cancel_key_input"))
async def cancel_key_input(callback: CallbackQuery, state: FSMContext, bot:Bot):
        await state.clear()
        await callback.message.edit_text("Ввод ключа отменён.")
        await bot.send_message(text = "Главное меню:", chat_id=callback.from_user.id, reply_markup=get_main_keyboard())
        await callback.answer()


@router.message(F.text == "Создать проект")
async def create_project(message: Message, state: FSMContext):
    await state.clear()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_project_naming")]
              ],
        resize_keyboard=True
    )
    await message.answer("Внимание: сейчас будет вызвана процедура создания проекта. Далее Вам необходимо ввести название проекта и его описание.", reply_markup=ReplyKeyboardRemove())
    await message.answer("Как назовем проект?", reply_markup=keyboard)
    
    await state.set_state(CreateProjectForm.waiting_for_project_name)


@router.message(CreateProjectForm.waiting_for_project_name)
async def process_project_name(message: Message, state: FSMContext):
    project_name = message.text
    await state.update_data(project_name=project_name)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_project_naming")],
            [InlineKeyboardButton(text="⬅️ Назад к выбору имени", callback_data="back_to_name")]
        ],
        resize_keyboard=True
    )
    await message.answer(f"Имя твоего проекта - {project_name}.")
    await message.answer(f"Перейдём к описанию проекта. Учти, что на основе него GigaChat будет выдавать анализ выполнения проекта, поэтому стоит расписать детали более подробно.", reply_markup=keyboard)
    await state.set_state(CreateProjectForm.waiting_for_project_description)

@router.callback_query(F.data == "back_to_name")
async def back_to_project_name(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CreateProjectForm.waiting_for_project_name)
    await callback.message.edit_text("Введите новое имя проекта:")
    await callback.answer()


@router.message(CreateProjectForm.waiting_for_project_description)
async def process_project_description(message: Message, state: FSMContext):
    project_desc = message.text
    user_id = message.from_user.id
    session = create_db_session(DATABASE_URL)
    project_key = generate_unique_project_key()
    data = await state.get_data()
    project_name = data.get("project_name")
    project = Project(name=project_name, description=project_desc, owner_id=user_id, project_key=project_key)
    session.add(project)
    session.flush()
    user_project_association = UserProjectAssociation(user_id=user_id, project_id=project.project_id,
                                                      role="Администратор")
    session.add(user_project_association)
    session.commit()
    session.close()
    await message.answer(f"Проект '{project_name}' создан! Ты являешься администратором.",
                         reply_markup=get_main_keyboard())
    await message.answer(f"Ключ для присоединения к проекту: `{project_key}`", parse_mode="Markdown")
    await state.clear()

@router.message(F.text=="Присоединиться к проекту")
async def join_project_command(message: Message, state: FSMContext):
    await state.clear()  # Добавляем сброс состояния
    logging.info(FSMContext)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌Отмена❌", callback_data="cancel_key_input", )]
              ],
        resize_keyboard=True
    )
    await message.answer("Для того чтобы присоединиться к проекту вам надо ввести его ключ", reply_markup=ReplyKeyboardRemove())
    await message.answer("Введите ключ проекта:", reply_markup=keyboard)
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
async def process_project_key(message: Message, state: FSMContext, bot:Bot):
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



def schedule_deadline_notification(task_id, deadline_date, bot: Bot):
    notification_time = deadline_date - timedelta(days=1)  # Уведомление за 1 день до дедлайна
    trigger = DateTrigger(run_date=notification_time)

    async def send_notification(task_id, bot: Bot):
        session = create_db_session(DATABASE_URL)  # Новая сессия
        task = session.query(Task).get(task_id)
        project = session.query(Project).join(TaskProjectAssociation).filter(TaskProjectAssociation.task_id == task_id).first()
        if task and project:
            user_ids = [assoc.user_id for assoc in session.query(UserProjectAssociation).filter(UserProjectAssociation.project_id == project.project_id).all()]
            for user_id in user_ids:
                try:
                    await bot.send_message(user_id, f"Напоминание: приближается дедлайн задачи '{task.name}' в проекте '{project.name}'. Дедлайн: {task.deadline_date.strftime('%d.%m.%Y')}")
                except Exception as e:
                    logging.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
        session.close()
        # Удаляем задачу из планировщика после отправки уведомления
        try:
            scheduler.remove_job(f"notification_{task_id}")
            logging.info(f"Задача уведомления для задачи {task_id} удалена из планировщика.")
        except Exception as e:
            logging.error(f"Ошибка удаления задачи уведомления: {e}")



    scheduler.add_job(send_notification, trigger=trigger, args=[task_id, bot], id=f"notification_{task_id}")
    logging.info(f"Задача уведомления для задачи {task_id} запланирована на {notification_time}")

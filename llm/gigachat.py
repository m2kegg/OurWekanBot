import os
from langchain_gigachat import GigaChat
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate

from config import DATABASE_URL
from data.models import create_db_session, Project, TaskProjectAssociation, User, \
    UserTaskAssociation, Task, TaskEnum


def analyze_employee(employee_id: int, project_id: int):
    try:
        api_key = os.environ.get("GIGACHAT_API_KEY")
        if not api_key:
            print("Необходимо установить переменную окружения GIGACHAT_API_KEY")
            exit()

        gigachat = GigaChat(credentials=api_key, verify_ssl_certs=False)

        template = """
        Ты - проджект-менеджер, который на основе статистики работы над задачами (количеству часов)
        анализирует производительность сотрудника. Проанализируй, пожалуйста, производительность данного сотрудника.
        Является ли сотрудник проблемным? Закрывает ли сотрудник достаточно задач (по сравнению с другими)?

        Название проекта: {project_name}
        Описание проекта: {project_desc}
        ФИО Сотрудника: {name}
        Задачи, выполненные сотрудником в рамках проекта:
        {tasks}
        Количество часов, закрытое в проекте этим сотрудником: {hours_one}
        Количество часов, закрытое в проекте всеми сотрудниками: {hours_all}
        """

        session = create_db_session(DATABASE_URL)
        project = session.query(Project).get(project_id)
        user = session.query(User).get(employee_id)
        tasks = session.query(Task).join(TaskProjectAssociation).filter(
            TaskProjectAssociation.project_id == project_id
        ).join(UserTaskAssociation).filter(
            UserTaskAssociation.user_id == employee_id
        ).filter(Task.State == TaskEnum.DONE).all()
        task_all_hours = session.query(Task).join(TaskProjectAssociation).filter(
            TaskProjectAssociation.project_id == project_id
        ).filter(Task.State == TaskEnum.DONE).all()

        prompt = PromptTemplate(template=template,
                                input_variables=["project_name", "project_desc", "name", "tasks", "hours_one",
                                                 "hours_all"])
        llm_chain = LLMChain(prompt=prompt, llm=gigachat)

        project_name = project.name
        project_desc = project.description
        employee_name = user.fullname

        tasks_string = ""
        employee_total_hours = 0
        for task in tasks:
            tasks_string += f"Название задания: {task.name}\n"
            tasks_string += f"Описание задания: {task.description}\n"
            tasks_string += f"Количество часов, потраченное на задание: {task.time_taken}\n"
            employee_total_hours += task.time_taken

        total_project_hours = 0
        for task in task_all_hours:
            total_project_hours += task.time_taken

        result = llm_chain.run(project_name=project_name,
                               project_desc=project_desc,
                               name=employee_name,
                               tasks=tasks_string,
                               hours_one=employee_total_hours,
                               hours_all=total_project_hours)
        return result

    except Exception as e:
        print(f"Произошла ошибка: {e}")


def predict_project_risks(project_id: int):
    try:
        api_key = os.environ.get("GIGACHAT_API_KEY")
        if not api_key:
            print("Необходимо установить переменную окружения GIGACHAT_API_KEY")
            exit()

        gigachat = GigaChat(credentials=api_key, verify_ssl_certs=False)

        session = create_db_session(DATABASE_URL)
        project = session.query(Project).get(project_id)

        template = """
        Ты - опытный проектный менеджер. Проанализируй, пожалуйста, название и описание проекта и перечисли возможные проблемы и риски, которые могут возникнуть в ходе выполнения данного проекта.

        Название проекта: {project_name}
        Описание проекта: {project_description}

        Возможные проблемы и риски:
        """

        prompt = PromptTemplate(template=template,
                                input_variables=["project_name", "project_description"])
        llm_chain = LLMChain(prompt=prompt, llm=gigachat)

        result = llm_chain.run(project_name=project.name, project_description=project.description)
        return result

    except Exception as e:
        print(f"Произошла ошибка при анализе рисков проекта: {e}")

def get_task_advice(task_id: int):
    try:
        api_key = os.environ.get("GIGACHAT_API_KEY")
        if not api_key:
            print("Необходимо установить переменную окружения GIGACHAT_API_KEY")
            exit()

        gigachat = GigaChat(credentials=api_key, verify_ssl_certs=False)

        session = create_db_session(DATABASE_URL)
        task = session.query(Task).get(task_id)

        if not task:
            return f"Задача с ID {task_id} не найдена."

        template = """
        Ты - опытный наставник, помогающий сотрудникам выполнять задачи.
        Проанализируй, пожалуйста, описание задачи и дай советы по её выполнению,
        учитывая, что это может быть сложная или новая задача для исполнителя.

        Название задачи: {task_name}
        Описание задачи: {task_description}

        Советы по выполнению:
        """

        prompt = PromptTemplate(template=template,
                                input_variables=["task_name", "task_description"])
        llm_chain = LLMChain(prompt=prompt, llm=gigachat)

        result = llm_chain.run(task_name=task.name, task_description=task.description)
        return result

    except Exception as e:
        print(f"Произошла ошибка при анализе задачи: {e}")
        return f"Произошла ошибка при анализе задачи: {e}"
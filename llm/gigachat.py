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

        gigachat = GigaChat(credentials=api_key)

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
                                input_variables=["project_name", "project_desc", "name", "tasks", "hours_one", "hours_all"])
        llm_chain = LLMChain(prompt=prompt, llm=gigachat)

        project_name = project.name
        project_desc = project.description
        employee_name = user.name


        tasks_string = ""
        cur_task_string = ""
        for task in tasks:
            cur_task_string += f"Название задания: {task.name}\n"
            cur_task_string += f"Описание задания: {task.description}\n"
            cur_task_string += f"Количество часов, потраченное на задание: {task.time_taken}\n"
            tasks_string += cur_task_string
            cur_task_string = ""



        result = llm_chain.run()
        return result

    except Exception as e:
        print(f"Произошла ошибка: {e}")

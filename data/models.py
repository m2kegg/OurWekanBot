from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Boolean, Date, UnicodeText, Enum
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
import enum
import uuid

SQLAlchemyBase = declarative_base()

class TaskEnum(enum.Enum):
    CREATED = "CREATED"
    IN_WORK = "IN_WORK"
    ON_REVISION = "ON_REVISION"
    DONE = "DONE"
    
class User(SQLAlchemyBase):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)
    fullname = Column(String)

    projects = relationship("UserProjectAssociation", back_populates="user")
    tasks = relationship("UserTaskAssociation", back_populates="users")

class Project(SQLAlchemyBase):
    __tablename__ = "projects"

    project_id = Column(Integer, primary_key=True)
    name = Column(String)
    owner_id = Column(Integer, ForeignKey("users.user_id"))
    project_key = Column(String, unique=True, index=True)  # Добавляем поле для ключа проекта
    

    owner = relationship("User")
    users = relationship("UserProjectAssociation", back_populates="project")
    tasks =  relationship("TaskProjectAssociation", back_populates="project")

class Task(SQLAlchemyBase):
    __tablename__ = "tasks"

    name = Column(String)
    task_id = Column(Integer, primary_key=True)
    description = Column(UnicodeText)
    project_id = Column(Integer, ForeignKey("projects.project_id"), primary_key=True)
    start_date = Column(Date)
    deadline_date = Column(Date)
    time_taken=Column(Integer)
    State = Column(Enum(TaskEnum))

    project = relationship("TaskProjectAssociation", back_populates="task")
    users = relationship("UserTaskAssociation", back_populates="tasks")

class UserProjectAssociation(SQLAlchemyBase):
    __tablename__ = "user_project_association"

    user_id = Column(Integer, ForeignKey("users.user_id"), primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.project_id"), primary_key=True)
    role = Column(String)

    user = relationship("User", back_populates="projects")
    project = relationship("Project", back_populates="users")

class UserTaskAssociation(SQLAlchemyBase):
    __tablename__ = "user_task_association"

    user_id = Column(Integer, ForeignKey("users.user_id"), primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.task_id"), primary_key=True)

    users = relationship("User", back_populates="tasks")
    task = relationship("Task", back_populates="users")

class TaskProjectAssociation(SQLAlchemyBase):
    __tablename__ = "task_project_association"

    task_id = Column(Integer, ForeignKey("tasks.task_id"), primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.project_id"), primary_key=True)
    

    task = relationship("Task", back_populates="project")
    project = relationship("Project", back_populates="tasks")
   




def create_db_session(database_url):
    engine = create_engine(database_url)
    SQLAlchemyBase.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()
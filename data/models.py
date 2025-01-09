from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
import uuid

SQLAlchemyBase = declarative_base()

class User(SQLAlchemyBase):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)
    fullname = Column(String)

    projects = relationship("UserProjectAssociation", back_populates="user")

class Project(SQLAlchemyBase):
    __tablename__ = "projects"

    project_id = Column(Integer, primary_key=True)
    name = Column(String)
    owner_id = Column(Integer, ForeignKey("users.user_id"))
    project_key = Column(String, unique=True, index=True)  # Добавляем поле для ключа проекта

    owner = relationship("User")
    users = relationship("UserProjectAssociation", back_populates="project")

class UserProjectAssociation(SQLAlchemyBase):
    __tablename__ = "user_project_association"

    user_id = Column(Integer, ForeignKey("users.user_id"), primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.project_id"), primary_key=True)
    role = Column(String)

    user = relationship("User", back_populates="projects")
    project = relationship("Project", back_populates="users")

def create_db_session(database_url):
    engine = create_engine(database_url)
    SQLAlchemyBase.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()
class LogRecord(Base):
    __tablename__ = 'log_records'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    username = Column(String)
    fullname = Column(String)
    action_type = Column(String)
    content = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<LogRecord(user_id={self.user_id}, username='{self.username}', action_type='{self.action_type}')>"

class DatabaseLoggingMiddleware(BaseMiddleware):
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

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

        db = self.SessionLocal()
        try:
            log_record = LogRecord(
                user_id=user_id,
                username=user_username,
                fullname=user_fullname,
                action_type=action_type,
                content=content
            )
            db.add(log_record)
            db.commit()
        except Exception as e:
            logging.error(f"Error saving log to database: {e}")
            db.rollback()
        finally:
            db.close()

        return await handler(event, data)
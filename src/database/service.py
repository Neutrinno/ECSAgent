from pathlib import Path
import platform
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional

from src.database.models import Base
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SQLiteService:
    """
    Сервис для работы с базой данных отчетов по площадям
    """
    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string or self._get_default_connection_string()
        self.engine = create_engine(
            self.connection_string,
            connect_args={"check_same_thread": False},
            echo=False
        )
        self.session_factory = scoped_session(
            sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False
            )
        )
        self._init_db()

    def _get_default_connection_string(self) -> str:
        """
        Генерирует строку подключения по умолчанию для базы отчетов
        """
        db_name = "ecs_assistant.db"
        app_dir = self._get_app_data_dir()
        app_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{app_dir / db_name}"

    @staticmethod
    def _get_app_data_dir() -> Path:
        """
        Возвращает путь к директории приложения в зависимости от ОС
        """
        home = Path.home()
        app_name = "ECSAssistant"

        if platform.system() == "Windows":
            return home / "AppData" / "Local" / app_name / "Database"
        elif platform.system() == "Darwin":
            return home / "Library" / "Application Support" / app_name / "Database"
        return home / f".{app_name.lower()}" / "database"

    def _init_db(self):
        """
        Инициализирует таблицы БД для отчетов по площадям
        """
        try:
            Base.metadata.create_all(self.engine)
            logger.info(f"База данных отчетов инициализирована: {self.connection_string}")
        except SQLAlchemyError as e:
            logger.error(f"Ошибка инициализации базы данных отчетов: {str(e)}")
            raise

    def get_session(self):
        """Возвращает новую сессию БД"""
        return self.session_factory()

    def __enter__(self):
        """Поддержка контекстного менеджера"""
        self.session = self.get_session()
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Завершение работы контекстного менеджера"""
        self.session.close()

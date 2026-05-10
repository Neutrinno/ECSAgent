from pathlib import Path
import sys
import platform
from sqlalchemy import create_engine, inspect, text

current_script_dir = Path(__file__).parent
project_root = current_script_dir.parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from src.database.models import Base

    print("Импорт Base прошел успешно")
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    sys.exit(1)

from src.utils.logger import get_logger

logger = get_logger(__name__)


def get_default_db_path() -> Path:
    """Возвращает путь к базе данных по умолчанию"""
    db_name = "ecs_assistant.db"
    home = Path.home()

    if platform.system() == "Windows":
        app_dir = home / "AppData" / "Local" / "ECSAssistant" / "Database"
    elif platform.system() == "Darwin":
        app_dir = home / "Library" / "Application Support" / "ECSAssistant" / "Database"
    else:  # Linux
        app_dir = home / ".ecs_assistant" / "database"

    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir / db_name


def recreate_specific_tables(tables: list):
    """
    Удаляет и пересоздает указанные таблицы
    """
    try:
        db_path = get_default_db_path()
        connection_string = f"sqlite:///{db_path}"
        engine = create_engine(
            connection_string,
            connect_args={"check_same_thread": False}
        )

        inspector = inspect(engine)

        with engine.begin() as connection:
            for table_name in tables:
                if table_name in inspector.get_table_names():
                    connection.execute(text("PRAGMA foreign_keys = OFF"))
                    connection.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
                    print(f"Таблица {table_name} удалена")
                    connection.execute(text("PRAGMA foreign_keys = ON"))

            for table in Base.metadata.sorted_tables:
                if table.name in tables:
                    table.create(connection)
                    print(f"Таблица {table.name} создана")

        print(f"\nТаблицы {tables} успешно пересозданы")
        return True

    except Exception as e:
        print(f"Ошибка при обновлении таблиц: {str(e)}")
        return False


if __name__ == "__main__":
    TABLES_TO_RECREATE = [
        # 'new_solution',
        # 'vsp_core',
        # 'vsp_address',
        # 'vsp_timeline',
        # 'vsp_area',
        # 'vsp_workplace',
        # 'vsp_operations',
        # 'vsp_property',
        'client_flow'
    ]

    print("Таблицы для пересоздания:")
    for i, table in enumerate(TABLES_TO_RECREATE, 1):
        print(f"  {i}. {table}")

    confirm = input(f"\nПересоздать эти таблицы? Все данные будут потеряны! [y/N]: ")

    if confirm.lower() == 'y':
        print("\nНачинаю пересоздание...")
        success = recreate_specific_tables(TABLES_TO_RECREATE)

        if success:
            print("\n✅ Таблицы успешно пересозданы")
        else:
            print("\n❌ Ошибка при пересоздании таблиц")
    else:
        print("\nОтменено")

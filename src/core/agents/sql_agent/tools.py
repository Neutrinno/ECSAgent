from sqlalchemy import inspect, text
from typing import List, Dict, Any

from langchain.tools import tool

from src.core.agents.service_manager import service_manager
from src.core.agents.sql_agent.constant import COLUMN_COMMENTS, TABLE_DESCRIPTIONS


def _get_db_service():
    """
    Получает экземпляр SQLiteService из ServiceManager.
    Использует ленивую загрузку для избежания циклических импортов.
    """

    return service_manager.db_service


TARGET_TABLES = {
    "vsp_core",
    "vsp_address",
    "vsp_timeline",
    "vsp_area",
    "vsp_workplace",
    "vsp_operations",
    "vsp_property",
    "new_solution",
    "client_flow",  # поле под агента ClientFlow
}


def _format_schema(table_name: str, inspector) -> str:
    columns = inspector.get_columns(table_name)
    pk_constraint = inspector.get_pk_constraint(table_name)
    primary_keys = pk_constraint.get("constrained_columns", []) if pk_constraint else []
    foreign_keys = inspector.get_foreign_keys(table_name)

    schema_info = [f"Схема таблицы '{table_name}': ", "\nКолонки:"]

    for column in columns:
        column_info = f" - {column['name']}: {column['type']}"
        if not column.get("nullable", True):
            column_info += " NOT NULL"
        if column.get("default") is not None:
            column_info += f" DEFAULT {column['default']}"
        if column["name"] in primary_keys:
            column_info += " (PRIMARY KEY)"
        if column["name"] in COLUMN_COMMENTS:
            column_info += f" | Комментарий: '{COLUMN_COMMENTS[column['name']]}'"
        schema_info.append(column_info)

    if primary_keys:
        schema_info.append(f"\nПервичный ключ: {', '.join(primary_keys)}")

    if foreign_keys:
        schema_info.append("\nВнешние ключи:")
        for fk in foreign_keys:
            fk_info = f" - {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}"
            schema_info.append(fk_info)

    return "\n".join(schema_info)


# == Metadata tools ==
@tool
def list_tables() -> List[str]:
    """
    Возвращает список доступных таблиц (vsp_* и new_solution).
    """
    db_service = _get_db_service()
    inspector = inspect(db_service.engine)
    existing = set(inspector.get_table_names())
    available = sorted(list(existing.intersection(TARGET_TABLES)))
    return available


@tool
def list_tables_with_descriptions() -> List[Dict[str, str]]:
    """
    Возвращает список доступных таблиц (vsp_* и new_solution)
    с краткими текстовыми описаниями.
    """
    db_service = _get_db_service()
    inspector = inspect(db_service.engine)
    existing = set(inspector.get_table_names())
    available = sorted(list(existing.intersection(TARGET_TABLES)))

    return [
        {
            "name": table,
            "description": TABLE_DESCRIPTIONS.get(table, ""),
        }
        for table in available
    ]


@tool
def get_table_schema(table_name: str) -> str:
    """
    Возвращает схему указанной таблицы: колонки, типы, PK/FK, комментарии.
    Поддерживаются таблицы vsp_* и new_solution.
    """
    try:
        db_service = _get_db_service()
        inspector = inspect(db_service.engine)
        existing = set(inspector.get_table_names())

        if table_name not in existing or table_name not in TARGET_TABLES:
            return f"Таблица '{table_name}' недоступна. Доступные: {sorted(existing.intersection(TARGET_TABLES))}"

        return _format_schema(table_name, inspector)
    except Exception as e:
        return f"Ошибка при получении схемы таблицы '{table_name}': {str(e)}"


@tool
def get_all_schemas() -> str:
    """
    Возвращает схемы всех доступных таблиц (vsp_* и new_solution).
    """
    try:
        db_service = _get_db_service()
        inspector = inspect(db_service.engine)
        existing = set(inspector.get_table_names())
        targets = sorted(list(existing.intersection(TARGET_TABLES)))

        if not targets:
            return "Таблицы vsp_* и new_solution не найдены."

        parts = []
        for table in targets:
            parts.append(_format_schema(table, inspector))
        return "\n\n".join(parts)
    except Exception as e:
        return f"Ошибка при получении схем всех таблиц: {str(e)}"


# == Query Tools==
@tool
def execute_sql_query(sql_query: str) -> List[Dict[str, Any]]:
    """
    Выполняет SQL SELECT запрос к базе данных. ТОЛЬКО ДЛЯ ЧТЕНИЯ.

    Аргументы:
    - sql_query: строка с SQL SELECT запросом

    Важные ограничения:
    - Только SELECT запросы (INSERT/UPDATE/DELETE блокируются)
    - Всегда сначала используй get_table_schema / get_all_schemas
    - Возвращает данные в формате [{колонка: значение}, ...]
    - При ошибке возвращает [{"error": "сообщение"}]
    - Должен быть чистый SQL запрос без лишних комментариев и команд консоли
    """

    try:
        if not sql_query.strip().upper().startswith('SELECT'):
            return [{"error": "Only SELECT queries allowed"}]

        db_service = _get_db_service()
        with db_service.engine.connect() as connection:
            result = connection.execute(text(sql_query))
            columns = result.keys()
            return [dict(zip(columns, row)) for row in result.fetchall()]

    except Exception as e:
        return [{"error": f"SQL error: {str(e)}"}]

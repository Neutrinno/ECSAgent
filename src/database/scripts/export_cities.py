from pathlib import Path
import sys
import re
from sqlalchemy import text

current_script_dir = Path(__file__).parent
project_root = current_script_dir.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.service import SQLiteService
from src.utils.logger import get_logger

logger = get_logger(__name__)

OUTPUT_FILE = project_root / "data" / "cities_cleaned.txt"


def clean_city_name(city: str) -> str:
    """
    Очищает название города от префиксов и районов,
    а также приводит к формату с дефисами вместо пробелов.

    Удаляет:
    - Префиксы: г., с., пгт., пос., д., п., ст., х., аул, станица, ст-ца
    - Районы в скобках: (р-н Белгородский)
    - Лишние пробелы

    Преобразует:
    - Пробелы между словами → дефисы
    - Удаляет лишние дефисы (двойные и т.д.)
    """
    if not city:
        return ""

    cleaned = str(city).strip()


    prefix_pattern = r'^(г\.|с\.|пгт\.|пос\.|д\.|п\.|ст\.|х\.|рп\.|мкр\.|нп\.|аул|станица|ст-ца)\s*'
    cleaned = re.sub(prefix_pattern, '', cleaned, flags=re.IGNORECASE)
    district_pattern = r'\s*\([^)]*р-н[^)]*\)'
    cleaned = re.sub(district_pattern, '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*\([^)]+\)\s*$', '', cleaned)

    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'\s+', '-', cleaned)

    cleaned = re.sub(r'-+', '-', cleaned)
    cleaned = cleaned.strip('-')

    return cleaned


def export_cleaned_cities(db_service: SQLiteService):
    """
    Собирает city_id и city из базы, удаляет дубли по city_id,
    очищает названия и выводит в txt файл, отсортированный по city_id.
    """
    logger.info("Начинаю сбор и очистку названий городов...")

    with db_service.get_session() as session:
        query = text("""
            WITH city_stats AS (
                SELECT 
                    city_id,
                    city AS city_original,
                    COUNT(*) AS occurrence_count,
                    ROW_NUMBER() OVER (
                        PARTITION BY city_id 
                        ORDER BY COUNT(*) DESC
                    ) AS rn
                FROM vsp_core
                WHERE city_id IS NOT NULL 
                    AND city_id != ''
                    AND city IS NOT NULL
                    AND city != ''
                GROUP BY city_id, city
            )
            SELECT 
                city_id,
                city_original
            FROM city_stats
            WHERE rn = 1
            ORDER BY CAST(city_id AS INTEGER)  -- Сортировка по числовому значению city_id
        """)

        result = session.execute(query)
        rows = result.fetchall()

        if not rows:
            logger.warning("Не найдено записей с city_id в базе данных")
            return

        logger.info(f"Найдено {len(rows)} уникальных city_id")

        examples = []

        cities_list = []
        for row in rows:
            city_id = str(row[0]).strip()
            city_original = str(row[1]).strip()
            city_cleaned = clean_city_name(city_original)

            if city_cleaned:
                if city_original != city_cleaned and len(examples) < 10:
                    examples.append((city_original, city_cleaned))

                try:
                    city_id_int = int(city_id)
                    cities_list.append((city_id_int, city_id, city_cleaned))
                except ValueError:
                    cities_list.append((float('inf'), city_id, city_cleaned))
                    logger.warning(f"city_id '{city_id}' не является числом, будет помещён в конец списка")

        cities_list.sort(key=lambda x: x[0])

        cities_dict = {city_id: city_cleaned for _, city_id, city_cleaned in cities_list}

        logger.info(f"После очистки осталось {len(cities_dict)} городов")

        if examples:
            logger.info("\nПримеры очистки названий:")
            for original, cleaned in examples:
                logger.info(f"  '{original}' → '{cleaned}'")

        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write("{\n")
            items = list(cities_dict.items())
            for i, (city_id, city_cleaned) in enumerate(items):
                city_cleaned_escaped = city_cleaned.replace("'", "\\'").replace('"', '\\"')
                if i < len(items) - 1:
                    f.write(f"    '{city_id}': '{city_cleaned_escaped}', \n")
                else:
                    f.write(f"    '{city_id}': '{city_cleaned_escaped}'\n")
            f.write("}\n")

        logger.info(f"\nРезультат сохранен в файл: {OUTPUT_FILE}")
        logger.info(f"Всего записей: {len(cities_dict)}")
        logger.info(f"Отсортировано по возрастанию city_id")

        logger.info("\nПримеры результата (первые 10):")
        first_items = list(cities_dict.items())[:10]
        for i, (city_id, city_cleaned) in enumerate(first_items, 1):
            logger.info(f"  {i: 2}. '{city_id}': '{city_cleaned}'")

        if len(cities_dict) > 20:
            logger.info("\nПримеры результата (последние 10):")
            last_items = list(cities_dict.items())[-10:]
            for i, (city_id, city_cleaned) in enumerate(last_items, len(cities_dict) - 9):
                logger.info(f"  {i: 2}. '{city_id}': '{city_cleaned}'")

        num_ids = sum(1 for _, city_id, _ in cities_list if city_id.isdigit())
        non_num_ids = len(cities_dict) - num_ids

        if non_num_ids > 0:
            logger.warning(f"\nВнимание: {non_num_ids} city_id не являются числами и помещены в конец списка")


def main():
    """Главная функция для запуска скрипта"""
    db_service = SQLiteService()
    export_cleaned_cities(db_service)


if __name__ == "__main__":
    main()

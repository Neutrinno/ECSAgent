from typing import Optional, List
import json
from langgraph.types import Command
from langchain_core.tools import tool
from sqlalchemy import desc

from src.core.agents.service_manager import service_manager
from src.database.models import VSPCore
from src.utils.logger import get_logger

logger = get_logger(__name__)


@tool
def transfer_to_executor(
        agent_name: str,
        is_close: Optional[List[str]] = None,
        is_cs: Optional[List[str]] = None,
        is_bt: Optional[List[str]] = None,
        coordinates: Optional[str] = None
) -> Command:
    """
    Инструмент для передачи управления агенту-исполнителю с явным указанием параметров контекста.

    Args:
        agent_name: Имя агента-исполнителя
        is_close: Список номеров ВСП для закрытия
        is_cs: Список номеров ВСП для возврата в целевую сеть
        is_bt: Список номеров ВСП, которые примут клиентопоток
        coordinates: JSON-строка с координатами ВСП в формате '{"номер_всп": [широта, долгота]}'
    """
    update_data = {
        "current_agent": agent_name,
    }

    if is_close is not None or is_cs is not None or is_bt is not None or coordinates is not None:
        coords_dict = {}
        if coordinates:
            try:
                coords_json = json.loads(coordinates)
                for key, value in coords_json.items():
                    if isinstance(value, list) and len(value) == 2:
                        coords_dict[key] = (float(value[0]), float(value[1]))
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Ошибка парсинга coordinates: {e}")

        query_params = {
            "is_close": is_close or [],
            "is_cs": is_cs or [],
            "is_bt": is_bt or [],
            "coordinates": coords_dict,
        }
        update_data["query_params"] = query_params

        logger.info(f"Передача параметров агенту {agent_name}: "
                    f"is_close={query_params.is_close}, "
                    f"is_cs={query_params.is_cs}, "
                    f"is_bt={query_params.is_bt}, "
                    f"координат={len(query_params.coordinates)}")
    else:
        logger.info(f"Отправка агенту-исполнителю {agent_name} (без параметров)")
    return Command(
        goto=agent_name,
        update=update_data,
        graph=Command.PARENT,
    )


@tool
def get_urf_code(gosb_vsp: str) -> str:
    """
    Конвертирует номер ВСП в формате gosb_vsp (например, "9043_342" или "9043/342") в urf_code для работы агента.

    Автоматически нормализует формат: заменяет слеш (/) на подчеркивание (_).
    Примеры:
    - "9043_342" → ищет "9043_342"
    - "9043/342" → автоматически преобразуется в "9043_342" и ищет по этому значению
    - "8607_0197" → ищет "8607_0197"

    Args:
        gosb_vsp: Номер ВСП в формате gosb_vsp (может быть с подчеркиванием или слешем, например "9043_342" или "9043/342")

    Returns:
        urf_code в формате строки (например, "040_8607_0197") или сообщение об ошибке
    """
    logger.info(f"Поиск urf_code для gosb_vsp: {gosb_vsp}")

    if not gosb_vsp or not isinstance(gosb_vsp, str):
        error_msg = f"❌ Ошибка: gosb_vsp должен быть непустой строкой. Получено: {gosb_vsp}"
        logger.error(error_msg)
        return error_msg

    gosb_vsp = gosb_vsp.strip().replace('/', '_')

    if '_' not in gosb_vsp:
        error_msg = f"❌ Ошибка: неверный формат gosb_vsp. Ожидается формат 'XXXX_XXXXX' или 'XXXX/XXXXX' (например, '9043_342' или '9043/342'). Получено: '{gosb_vsp}'"
        logger.error(error_msg)
        return error_msg

    parts = gosb_vsp.split('_')
    if len(parts) < 2:
        error_msg = f"❌ Ошибка: неверный формат gosb_vsp. Ожидается формат 'XXXX_XXXXX' (например, '9043_342'). Получено: '{gosb_vsp}'"
        logger.error(error_msg)
        return error_msg

    logger.info(f"Нормализованный gosb_vsp: {gosb_vsp}")

    try:
        db_service = service_manager.db_service

        if db_service is None:
            error_msg = "❌ Ошибка: база данных не инициализирована"
            logger.error(error_msg)
            return error_msg


        with db_service.get_session() as session:
            vsp = session.query(VSPCore).filter(
                VSPCore.gosb_vsp == gosb_vsp
            ).order_by(desc(VSPCore.report_dt)).first()

            if vsp:
                urf_code = vsp.urf_code
                logger.info(f"Найден urf_code: {urf_code} для gosb_vsp: {gosb_vsp}")
                return urf_code
            else:
                error_msg = f"❌ ВСП с номером '{gosb_vsp}' не найден в базе данных. Проверьте правильность номера."
                logger.warning(error_msg)
                return error_msg

    except AttributeError as e:
        error_msg = f"❌ Ошибка доступа к базе данных: {str(e)}. Убедитесь, что ServiceManager инициализирован."
        logger.error(error_msg, exc_info=True)
        return error_msg
    except Exception as e:
        error_msg = f"❌ Ошибка при поиске urf_code для '{gosb_vsp}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg

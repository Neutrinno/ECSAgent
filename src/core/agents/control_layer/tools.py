from sqlalchemy import desc
from langchain_core.tools import tool

from src.core.agents.service_manager import service_manager
from src.database.models import VSPCore
from src.utils.logger import get_logger

logger = get_logger(__name__)


@tool
def get_urf_code(gosb_vsp: str) -> str:
    """
    Ищет urf_code по номеру ВСП в формате gosb_vsp.
    Принимает форматы вида 9043_342 или 9043/342.
    """
    logger.info("ControlLayer: поиск urf_code для gosb_vsp=%s", gosb_vsp)

    if not gosb_vsp or not isinstance(gosb_vsp, str):
        return f"❌ Ошибка: gosb_vsp должен быть непустой строкой. Получено: {gosb_vsp}"

    normalized = gosb_vsp.strip().replace("/", "_")
    if "_" not in normalized or len(normalized.split("_")) < 2:
        return (
            "❌ Ошибка: неверный формат gosb_vsp. Ожидается 'XXXX_XXXXX' или 'XXXX/XXXXX' "
            f"(например, '9043_342'). Получено: '{normalized}'"
        )

    try:
        db_service = service_manager.db_service
        if db_service is None:
            return "❌ Ошибка: база данных не инициализирована"

        with db_service.get_session() as session:
            vsp = (
                session.query(VSPCore)
                .filter(VSPCore.gosb_vsp == normalized)
                .order_by(desc(VSPCore.report_dt))
                .first()
            )
            if vsp:
                return vsp.urf_code
            return f"❌ ВСП с номером '{normalized}' не найден в базе данных. Проверьте правильность номера."
    except Exception as e:
        logger.error("ControlLayer: ошибка поиска urf_code: %s", e, exc_info=True)
        return f"❌ Ошибка при поиске urf_code для '{normalized}': {str(e)}"

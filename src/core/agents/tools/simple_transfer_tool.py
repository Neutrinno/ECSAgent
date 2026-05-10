from typing import Optional
from langgraph.types import Command
from langchain_core.tools import tool
from src.utils.logger import get_logger

logger = get_logger(__name__)


@tool
def transfer_to_executor(agent_name: str) -> Command:
    """
    Инструмент для передачи управления агенту-исполнителю с явным указанием параметров контекста.

    Args:
        agent_name: Имя агента-исполнителя
    """
    update_data = {
        "current_agent": agent_name,
    }

    logger.info("Отправка агенту-исполнителю: %s", agent_name)
    return Command(
        goto=agent_name,
        update=update_data,
        graph=Command.PARENT,
    )

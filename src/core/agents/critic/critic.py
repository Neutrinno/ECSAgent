from langchain_core.language_models import BaseChatModel

from src.core.graph_state import GraphState
from src.utils.logger import get_logger

logger = get_logger(__name__)

RETRY_LIMIT = 1


class Critic:
    """Базовый валидатор результата для итерации 2."""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    def process_state(self, state: GraphState) -> GraphState:
        state.current_agent = "critic"

        if state.final_result:
            state.status = "ok"
            state.need_retry = False
            state.need_replan = False
            logger.info("ThreadID: %s: Critic подтвердил результат", state.thread_id)
            return state

        state.retry_count += 1
        if state.retry_count <= RETRY_LIMIT:
            state.status = "in_progress"
            state.need_retry = True
            state.need_replan = False
            if not state.next_agent:
                state.next_agent = "sql_agent"
            logger.warning("ThreadID: %s: Critic запросил retry #%s", state.thread_id, state.retry_count)
            return state

        state.status = "failed"
        state.need_retry = False
        state.need_replan = False
        state.error = state.error or "No final_result after retry"
        logger.error("ThreadID: %s: Critic завершает с failed", state.thread_id)
        return state

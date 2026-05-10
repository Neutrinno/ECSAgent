from langchain_core.language_models import BaseChatModel

from src.core.graph_state import GraphState
from src.utils.logger import get_logger

logger = get_logger(__name__)


class Aggregator:
    """Агрегатор итогового ответа для sync-контура итерации 2."""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    def process_state(self, state: GraphState) -> GraphState:
        state.current_agent = "aggregator"

        if state.result:
            state.final_result = state.result
        elif state.intermediate_results:
            planner_summary = state.plan_summary or ""
            chunks = []
            if planner_summary:
                chunks.append(f"План: {planner_summary}")
            chunks.extend(f"{name}: {value}" for name, value in state.intermediate_results.items())
            state.final_result = "\n".join(chunks)
        else:
            state.final_result = None

        logger.info(
            "ThreadID: %s: Aggregator собрал финальный результат (len=%s)",
            state.thread_id,
            len(state.final_result or ""),
        )
        return state

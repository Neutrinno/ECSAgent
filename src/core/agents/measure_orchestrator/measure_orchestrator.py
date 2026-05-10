import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from src.core.agents.measure_orchestrator.measure_route_schema import MeasureRouteDecision
from src.core.agents.measure_orchestrator.system_prompt import MEASURE_CLASSIFIER_SYSTEM
from src.core.graph_state import GraphState
from src.utils.logger import get_logger

logger = get_logger(__name__)

_JSON_ROUTE_PATTERN = re.compile(r"\{[^{}]*\"route\"[^{}]*\}", re.DOTALL)


def _text_from_state(state: GraphState) -> str:
    parts: list[str] = []
    if state.messages:
        for m in state.messages:
            if isinstance(m, HumanMessage):
                c = m.content
                parts.append(c if isinstance(c, str) else str(c))
    if parts:
        return "\n\n".join(parts)
    return (state.user_query or "").strip()


class MeasureOrchestrator:
    """
    Роутер сценария ВСП: выставляет measure_route; переход к исполнителю — conditional_edges в графе.
    Без transfer_to_executor и без ParentCommand на этом шаге.
    """

    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self._prompt = ChatPromptTemplate.from_messages(
            [
                ("system", MEASURE_CLASSIFIER_SYSTEM.strip()),
                ("human", "{user_content}"),
            ]
        )
        try:
            self._structured = self._prompt | llm.with_structured_output(MeasureRouteDecision)
        except Exception as e:
            logger.warning("bind with_structured_output не удался (%s), только JSON-fallback", e)
            self._structured = None

    def _fallback_json(self, user_content: str) -> MeasureRouteDecision:
        raw = self.llm.invoke(
            [
                SystemMessage(
                    MEASURE_CLASSIFIER_SYSTEM.strip()
                    + '\nВерни только JSON: {"route":"network_optimizer_agent"} '
                    'или {"route":"relocation_agent"}.'
                ),
                HumanMessage(user_content),
            ]
        )
        text = raw.content if isinstance(raw.content, str) else str(raw.content)
        text = text.strip()
        try:
            return MeasureRouteDecision.model_validate_json(text)
        except Exception:
            pass
        m = _JSON_ROUTE_PATTERN.search(text)
        if m:
            return MeasureRouteDecision.model_validate_json(m.group(0))
        raise ValueError(f"Не удалось разобрать route: {text[:400]}")

    def _decide_route(self, user_content: str) -> MeasureRouteDecision:
        if self._structured is not None:
            try:
                return self._structured.invoke({"user_content": user_content})
            except Exception as e:
                logger.warning("structured_output не сработал (%s), JSON-fallback", e)
        return self._fallback_json(user_content)

    def process_state(self, state: GraphState) -> GraphState:
        try:
            logger.debug(f"ThreadID: {state.thread_id}: MeasureOrchestrator (route classifier)")
            state.current_agent = "measure_orchestrator"
            state.measure_route = None

            if not state.user_query and not state.messages:
                logger.error("No query or messages provided")
                state.error = "No query or messages provided"
                return state

            user_content = _text_from_state(state)
            if not user_content:
                logger.warning(
                    "ThreadID: %s: measure_orchestrator: пустой текст для классификации",
                    state.thread_id,
                )
                state.error = "Пустой текст для классификации measure_orchestrator"
                return state

            logger.info(f"ThreadID: {state.thread_id}: MeasureOrchestrator classifying route")
            decision = self._decide_route(user_content)
            state.measure_route = decision.route
            state.intermediate_results["measure_orchestrator_result"] = f"route={decision.route}"
            logger.info(f"ThreadID: {state.thread_id}: measure_route={decision.route}")
            return state

        except Exception as e:
            logger.error(f"ThreadID: {state.thread_id}: MeasureOrchestrator error: {e}")
            state.error = f"MeasureOrchestrator error: {str(e)}"
            state.measure_route = None
            state.intermediate_results["measure_orchestrator_error"] = {
                "error_type": type(e).__name__,
                "thread_id": str(state.thread_id),
                "agent": "measure_orchestrator",
            }
            return state

import json
import re
from typing import Any, Dict, List

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.core.agents.planner_agent.system_prompt import PLANNER_AGENT_PROMPT
from src.core.graph_state import GraphState
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PlannerDecision(BaseModel):
    next_agent: str = Field(description="Первый специализированный агент для запуска")
    plan_summary: str = Field(description="Краткая стратегия выполнения")
    plan_steps: List[str] = Field(default_factory=list, description="Пошаговый план выполнения")
    risks: List[str] = Field(default_factory=list, description="Риски и неопределенности")


class PlannerAgent:
    """
    Агент, который формирует по запросу пользователя определяет, какой агент продолжит работу
    """

    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self.prompt = PLANNER_AGENT_PROMPT
        self._prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self.prompt.strip()),
                ("human", "{user_content}"),
            ]
        )
        expected_vars = {"user_content"}
        actual_vars = set(self._prompt.input_variables)
        if actual_vars != expected_vars:
            logger.warning(
                "Planner prompt variables mismatch: expected=%s actual=%s",
                sorted(expected_vars),
                sorted(actual_vars),
            )
        try:
            self._structured = self._prompt | llm.with_structured_output(PlannerDecision)
        except Exception as e:
            logger.warning("Planner: structured_output недоступен (%s), используем JSON fallback", e)
            self._structured = None

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        cleaned = text.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError("Planner response does not contain JSON object")
        return json.loads(match.group(0))

    @staticmethod
    def _safe_next_agent(raw_value: Any) -> str:
        allowed = {
            "sql_agent",
            "client_flow_agent",
            "network_optimizer_agent",
            "relocation_agent",
            "acceptibility_agent"
        }
        value = str(raw_value or "").strip()
        if value in allowed:
            return value
        return "sql_agent"

    @staticmethod
    def _safe_list(raw_value: Any) -> List[str]:
        if not isinstance(raw_value, list):
            return []
        return [str(item).strip() for item in raw_value if str(item).strip()]

    def _decide_plan(self, user_content: str) -> Dict[str, Any]:
        if self._structured is not None:
            try:
                decision = self._structured.invoke({"user_content": user_content})
                if isinstance(decision, PlannerDecision):
                    return decision.model_dump()
                return decision
            except Exception as e:
                logger.warning("Planner: structured_output не сработал (%s), fallback", e)

        response = self.llm.invoke(
            [
                SystemMessage(content=self.prompt.strip()),
                HumanMessage(content=user_content),
            ]
        )
        raw_text = response.content if isinstance(response.content, str) else str(response.content)
        return self._extract_json(raw_text)

    def process_state(self, state: GraphState) -> GraphState:
        """
        Обрабатывает состояние графа и возвращает обновленное состояние.
        Planner формирует план и записывает его в state, без tools/goto-команд.
        """
        try:
            logger.debug(f"ThreadID: {state.thread_id}: Starting PlannerAgent processing")
            state.current_agent = "planner_agent"

            if not state.user_query and not state.messages:
                logger.error("No query or messages provided")
                state.error = "No query or messages provided"
                return state

            user_text = state.user_query
            if state.messages:
                last_human_messages = [
                    m.content for m in state.messages[-5:]
                    if isinstance(m, HumanMessage) and getattr(m, "content", None)
                ]
                if last_human_messages:
                    user_text = "\n".join(str(x) for x in last_human_messages)

            parsed: Dict[str, Any] = self._decide_plan(user_text)

            state.next_agent = self._safe_next_agent(parsed.get("next_agent"))
            state.plan_summary = str(parsed.get("plan_summary", "")).strip() or "План сформирован"
            state.plan_steps = self._safe_list(parsed.get("plan_steps"))[:8]
            if not state.plan_steps:
                state.plan_steps = [f"Вызвать {state.next_agent} для выполнения задачи"]
            state.plan_risks = self._safe_list(parsed.get("risks"))
            state.need_replan = False
            state.need_retry = False

            state.intermediate_results["planner_result"] = {
                "next_agent": state.next_agent,
                "plan_summary": state.plan_summary,
                "plan_steps": state.plan_steps,
                "plan_risks": state.plan_risks,
            }
            logger.info(
                "ThreadID: %s: Planner выбрал %s, steps=%s",
                state.thread_id,
                state.next_agent,
                len(state.plan_steps),
            )
            return state

        except Exception as e:
            logger.error(f"ThreadID: {state.thread_id}: PlannerAgent error: {str(e)}")
            state.error = f"PlannerAgent error: {str(e)}"
            state.need_replan = True
            state.intermediate_results["planner_error"] = {
                "error_type": type(e).__name__,
                "thread_id": str(state.thread_id),
                "agent": "planner_agent"
            }
            return state

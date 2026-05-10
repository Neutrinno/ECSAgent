import json
import re
from typing import Any, Dict, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from src.core.graph_state import GraphState
from src.core.agents.orchestrator.system_prompt import ORCHESTRATOR_AGENT_PROMPT
from src.utils.logger import get_logger

logger = get_logger(__name__)

SUPPORTED_AGENTS = {
    "sql_agent",
    "client_flow_agent",
    "network_optimizer_agent",
    "relocation_agent",
}


class Orchestrator:
    """Оркестратор single-step sync-контура итерации 2."""

    def __init__(self, llm: BaseChatModel, agent: Optional[Any] = None):
        self.llm = llm
        self.prompt = ORCHESTRATOR_AGENT_PROMPT
        if agent is not None:
            self.agent = agent
        elif self.llm is not None:
            self.agent = create_react_agent(
                model=self.llm,
                tools=[],
                prompt=self.prompt,
            )
        else:
            self.agent = None

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        cleaned = text.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _safe_next_agent(raw_value: Any) -> str:
        value = str(raw_value or "").strip()
        if value in SUPPORTED_AGENTS or value == "aggregator":
            return value
        return "aggregator"

    def _build_user_payload(self, state: GraphState) -> str:
        payload = {
            "user_query": state.user_query,
            "urf_codes": state.urf_codes,
            "plan_summary": state.plan_summary,
            "plan_steps": state.plan_steps,
            "current_next_agent": state.next_agent,
            "need_retry": state.need_retry,
            "last_result": state.result,
            "intermediate_results": state.intermediate_results,
        }
        return json.dumps(payload, ensure_ascii=False)

    def process_state(self, state: GraphState) -> GraphState:
        state.current_agent = "orchestrator"

        if state.need_replan:
            state.need_replan = False

        if state.need_retry and not state.next_agent:
            # Базовый retry-маршрут: повтор через SQL-ветку.
            state.next_agent = "sql_agent"

        if self.agent is not None:
            try:
                input_messages = state.messages.copy() if state.messages else []
                input_messages.append(HumanMessage(content=self._build_user_payload(state)))
                response = self.agent.invoke({"messages": input_messages})
                output_messages = response.get("messages") or []
                raw_text = ""
                for msg in output_messages:
                    if isinstance(msg, AIMessage) and msg.content:
                        raw_text = str(msg.content)
                parsed = self._extract_json(raw_text)
                llm_next_agent = self._safe_next_agent(parsed.get("next_agent"))

                if llm_next_agent == "aggregator" and state.need_retry and not state.next_agent:
                    state.next_agent = "sql_agent"
                else:
                    state.next_agent = llm_next_agent
                state.intermediate_results["orchestrator_decision"] = {
                    "next_agent": state.next_agent,
                    "reason": str(parsed.get("reason", "")).strip(),
                }
            except Exception as e:
                logger.warning("ThreadID: %s: Orchestrator react-agent fallback, reason=%s", state.thread_id, e)

        if state.next_agent in SUPPORTED_AGENTS or state.next_agent == "aggregator":
            logger.info("ThreadID: %s: Orchestrator выбрал %s", state.thread_id, state.next_agent)
            state.need_retry = False
            return state

        logger.info("ThreadID: %s: Orchestrator не получил next_agent, переход к aggregator", state.thread_id)
        state.next_agent = "aggregator"
        return state

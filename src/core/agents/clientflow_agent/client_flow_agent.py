import json
from datetime import date
from typing import Any, Dict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from src.core.agents.clientflow_agent.system_prompt import CLIENT_FLOW_PROMPT
from src.core.agents.sql_agent.tools import execute_sql_query, get_table_schema
from src.core.graph_state import GraphState, StepResult, as_graph_state
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _build_payload(state: GraphState, task: str, dependent_results: Dict[str, str]) -> str:
    """Формирует JSON-контекст для ReAct ClientFlow-агента."""
    payload: Dict[str, Any] = {
        "task": task,
        "urf_codes": state.urf_codes,
    }
    if dependent_results:
        payload["dependent_results"] = dependent_results
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _extract_result(response: dict) -> str:
    """Извлекает финальный текст ответа из истории сообщений ReAct-агента."""
    for msg in reversed(response.get("messages", [])):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content).strip()
    return ""


def _extract_tools_called(response: dict) -> list:
    """Извлекает список вызванных инструментов из истории сообщений."""
    tools_called = []
    for msg in response.get("messages", []):
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls"):
            for tc in msg.tool_calls or []:
                tools_called.append({
                    "tool": tc.get("name"),
                    "args": tc.get("args", {}),
                })
    return tools_called


class ClientFlowAgent:
    """
    Агент для анализа запроса клиентопотока по историческим данным
    """

    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self.tools = [
            get_table_schema,
            execute_sql_query,
        ]
        self.tools_description = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])

        self.prompt = CLIENT_FLOW_PROMPT.format(
            tools_description=self.tools_description,
            date=date.today().isoformat(),
        )
        self.agent = create_react_agent(model=self.llm,
                                        tools=self.tools,
                                        prompt=self.prompt)

    def process_state(self, state: GraphState) -> Dict[str, Any]:
        """Точка входа ноды. Возвращает патч GraphState."""
        state = as_graph_state(state)
        current_step_id = state.current_step_id
        if not current_step_id:
            msg = "ClientFlowAgent: current_step_id отсутствует, выполнение шага невозможно"
            logger.error("ThreadID: %s: %s", state.thread_id, msg)
            return {"error": msg}

        logger.debug(
            "ThreadID: %s: ClientFlowAgent старт (шаг: %s)",
            state.thread_id, current_step_id,
        )

        step = next((s for s in state.plan_steps if s.step_id == current_step_id), None)
        if not step:
            msg = f"ClientFlowAgent: шаг {current_step_id} не найден в plan_steps"
            logger.error("ThreadID: %s: %s", state.thread_id, msg)
            return {
                "step_results": {
                    current_step_id: StepResult(
                        agent="client_flow_agent",
                        task="guard_check",
                        result=msg,
                        status="failed",
                    )
                },
                "completed_steps": [current_step_id],
            }

        task = step.task
        dependent_results: Dict[str, str] = {}
        for dep_id in step.depends_on:
            dep = state.step_results.get(dep_id)
            if dep and dep.status == "ok" and dep.result:
                dependent_results[dep_id] = dep.result

        try:
            response = self.agent.invoke({
                "messages": [HumanMessage(content=_build_payload(state, task, dependent_results))]
            })
            final_text = _extract_result(response)
            tools_called = _extract_tools_called(response)
            logger.info(
                "ThreadID: %s: ClientFlowAgent завершён (шаг: %s, result_len=%d, tools=%d)",
                state.thread_id, current_step_id, len(final_text), len(tools_called),
            )

            step_result = StepResult(
                agent="client_flow_agent",
                task=task,
                result=final_text,
                tools_called=tools_called,
                status="ok",
            )

        except Exception as e:
            logger.error(
                "ThreadID: %s: ClientFlowAgent ошибка (шаг: %s): %s",
                state.thread_id, current_step_id, e, exc_info=True,
            )
            step_result = StepResult(
                agent="client_flow_agent",
                task=task,
                result=str(e),
                status="failed",
            )

        return {
            "step_results": {current_step_id: step_result},
            "completed_steps": [current_step_id],
        }

from typing import Any, Dict, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from src.core.agents.control_layer.system_prompt import (
    CONTROL_LAYER_CLARIFY_PROMPT,
    CONTROL_LAYER_PROMPT,
    DOMAIN_EXPLANATION,
)
from src.core.agents.control_layer.tools import get_urf_code
from src.core.graph_state import GraphState
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _extract_last_ai_text(messages: list) -> str:
    """Возвращает текст последнего AIMessage из списка сообщений."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content).strip()
    return ""


def _extract_tool_result(messages: list, tool_name: str) -> tuple[Optional[str], Optional[str]]:
    """
    Извлекает результат вызова инструмента из списка сообщений.
    Возвращает (result, error): одно из двух будет None.
    """
    for msg in messages:
        if isinstance(msg, ToolMessage) and getattr(msg, "name", "") == tool_name:
            content = str(msg.content or "").strip()
            if content.startswith("❌"):
                return None, content
            if content:
                return content, None
    return None, None


class ControlLayer:
    """Входная нода графа и единственная точка диалога с пользователем.

    Два режима работы:
    1. Первый вход (critic_issue_type is None) — интерпретирует запрос,
       резолвит urf_code, определяет нужен ли пайплайн или можно ответить напрямую.
    2. После критика с need_clarify — формулирует уточняющий вопрос пользователю
       на основе critic_feedback.

    Роутер route_from_control в graph.py читает поля state и принимает решение
    о следующем шаге — control_layer только пишет данные, не управляет маршрутом.
    """

    def __init__(self, llm: BaseChatModel, agent: Optional[Any] = None):
        self.llm = llm
        self.tools = [get_urf_code]

        tools_description = "\n".join(
            f"- {t.name}: {t.description}" for t in self.tools
        )
        prompt = CONTROL_LAYER_PROMPT.format(
            domain_explanation=DOMAIN_EXPLANATION,
            tools_description=tools_description,
        )
        self.agent = agent or create_react_agent(
            model=self.llm,
            tools=self.tools,
            prompt=prompt,
        )

    def process_state(self, state: GraphState) -> Dict[str, Any]:
        """Основная точка входа ноды. Возвращает патч GraphState."""

        # Успешный терминальный кейс после критика: не запускаем пайплайн заново.
        if state.status == "ok" and state.final_result:
            logger.info(
                "ControlLayer: status=ok и final_result присутствует -> завершаем без ре-инициализации"
            )
            return {"status": "ok", "final_result": state.final_result}

        # Критик исчерпал лимит retry — завершаем с честным сообщением
        if state.status == "failed":
            logger.warning("ControlLayer: получен status=failed от критика, завершаем")
            return {"status": "failed", "final_result": state.final_result}

        # Повторный вход после критика с need_clarify
        if state.critic_issue_type == "need_clarify":
            return self._handle_clarify(state)

        # Первый вход — интерпретация запроса
        return self._handle_initial(state)

    def _handle_initial(self, state: GraphState) -> Dict[str, Any]:
        """Первый вход: интерпретация запроса, резолюция urf_code."""
        messages = state.messages.copy()
        # user_query обычно уже добавлен в start_agent; добавляем только если история пуста.
        if not messages and state.user_query:
            messages.append(HumanMessage(content=state.user_query))

        response = self.agent.invoke({"messages": messages})
        output_messages = response.get("messages") or messages

        urf_code, tool_error = _extract_tool_result(output_messages, "get_urf_code")
        last_ai_text = _extract_last_ai_text(output_messages)

        # urf_code найден → передаём в planner
        if urf_code:
            logger.info("ControlLayer: urf_code найден: %s", urf_code)
            return {
                "messages": output_messages,
                "urf_codes": [urf_code],
                "control_layer_answer": None,
                "critic_issue_type": None,
                "status": "in_progress",
                "final_result": None,
            }

        # Инструмент вернул ошибку → просим уточнить номер ВСП
        if tool_error:
            logger.info("ControlLayer: ошибка get_urf_code: %s", tool_error)
            clarification = (
                "Не удалось найти ВСП по указанному номеру. "
                "Пожалуйста, уточните номер в формате XXXX_XXXXX (например, 9043_342)."
            )
            return {
                "messages": output_messages,
                "control_layer_answer": clarification,
                "critic_issue_type": "need_clarify",
                "status": "in_progress",
                "final_result": None,
            }

        # Прямой ответ без пайплайна (общий вопрос, приветствие и т.п.)
        direct_answer = last_ai_text or "Уточните запрос, чтобы я мог помочь точнее."
        logger.info("ControlLayer: прямой ответ без пайплайна")
        return {
            "messages": output_messages,
            "control_layer_answer": direct_answer,
            "critic_issue_type": None,
            "status": "ok",
            "final_result": direct_answer,
        }

    def _handle_clarify(self, state: GraphState) -> Dict[str, Any]:
        """Повторный вход после critic need_clarify: формулируем вопрос пользователю."""
        logger.info("ControlLayer: формулировка уточняющего вопроса (need_clarify)")

        prompt = CONTROL_LAYER_CLARIFY_PROMPT.format(
            domain_explanation=DOMAIN_EXPLANATION,
            user_query=state.user_query,
            critic_feedback=state.critic_feedback or "Недостаточно данных для анализа.",
        )
        response = self.llm.invoke([HumanMessage(content=prompt)])
        clarification = str(response.content).strip()

        return {
            "messages": state.messages + [AIMessage(content=clarification)],
            "control_layer_answer": clarification,
            "critic_issue_type": "need_clarify",  # роутер увидит → end
            "status": "in_progress",
            "final_result": None,
        }
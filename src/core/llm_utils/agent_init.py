from typing import Dict, Any
from uuid import uuid4, UUID
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage, HumanMessage
import ast

from src.core.agents.service_manager import service_manager
from src.core.graph_state import GraphState
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _format_message_for_debug(message: BaseMessage) -> Dict[str, Any]:
    """Форматирует сообщение для отладочного вывода"""
    msg_info = {
        "type": type(message).__name__,
        "content": message.content
    }

    if isinstance(message, ToolMessage):
        msg_info["tool_call_id"] = getattr(message, "tool_call_id", None)
        msg_info["name"] = getattr(message, "name", None)

    if isinstance(message, AIMessage):
        if hasattr(message, "tool_calls") and message.tool_calls:
            msg_info["tool_calls"] = [
                {"name": tc.get("name"), "args": tc.get("args", {})}
                for tc in message.tool_calls
            ]

    return msg_info


def _format_state_for_debug(final_state) -> Dict[str, Any]:
    """Форматирует состояние графа для читабельного отображения"""

    def _get(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    if isinstance(final_state, dict) and "state" in final_state and isinstance(final_state["state"], str):
        try:
            parsed = ast.literal_eval(final_state["state"])
            if isinstance(parsed, dict):
                final_state = {**final_state, **parsed}
        except Exception:
            pass

    thread_id = _get(final_state, 'thread_id')
    user_query = _get(final_state, 'user_query')
    current_agent = _get(final_state, 'current_agent')
    result = _get(final_state, 'result')
    final_result = _get(final_state, 'final_result')
    error = _get(final_state, 'error')
    messages = _get(final_state, 'messages', []) or []
    if not isinstance(messages, list):
        messages = [messages]
    intermediate_results = _get(final_state, 'intermediate_results') or {}
    if not isinstance(intermediate_results, dict):
        intermediate_results = {}

    if not any([thread_id, user_query, current_agent, result, final_result, error, messages, intermediate_results]):
        return {"state": str(final_state), "type": type(final_state).__name__}

    debug_info = {
        "thread_id": thread_id,
        "user_query": user_query,
        "current_agent": current_agent,
        "result": result,
        "final_result": final_result,
        "error": error,
    }

    if messages:
        debug_info["messages"] = [
            _format_message_for_debug(msg)
            for msg in messages
        ]
        debug_info["total_messages"] = len(messages)

    if intermediate_results:
        debug_info["intermediate_results"] = {
            k: v
            for k, v in list(intermediate_results.items())
        }

    return debug_info


def start_agent(user_query: str, thread_id: UUID = None):
    """
    Запускает выполнение графа агентов для обработки запроса.

    Args:
        user_query (str): Запрос пользователя для анализа
        thread_id (UUID, optional): Идентификатор сессии. Если None - создается новый

    Returns:
        Dict: Результат выполнения с ключами:
            - result: финальный результат (если успех)
            - error: сообщение об ошибке (если ошибка)
            - thread_id: идентификатор сессии
            - tokens_used: словарь с использованием токенов по агентам
            - final_state: полное состояние выполнения (для отладки)
    """
    try:
        logger.debug("Получение агентов из ServiceManager...")

        if not service_manager.is_initialized:
            logger.info("ServiceManager не инициализирован, выполняем инициализацию...")
            service_manager.initialize()

        graph = service_manager.agent_graph
        logger.debug("Граф агентов получен из ServiceManager")

        if thread_id is None:
            thread_id = uuid4()
            logger.info(f"Сгенерирован новый thread_id: {thread_id}")
        else:
            logger.info(f"Используется существующий thread_id: {thread_id}")

        logger.info(f"ThreadID: {thread_id}: Получен запрос: {user_query}")

        config = {"configurable": {"thread_id": str(thread_id)}}
        previous_messages = []
        try:
            snapshot = graph.get_state(config)
            if snapshot and getattr(snapshot, "values", None):
                prev_values = snapshot.values
                if isinstance(prev_values, dict):
                    previous_messages = prev_values.get("messages", []) or []
                else:
                    previous_messages = getattr(prev_values, "messages", []) or []
        except Exception as state_error:
            logger.debug(
                f"ThreadID: {thread_id}: Не удалось получить предыдущий state из memory: {state_error}"
            )

        initial_state = GraphState(
            messages=[*previous_messages, HumanMessage(content=user_query)],
            user_query=user_query,
            thread_id=thread_id,
            current_agent=None,
            final_result=None,
            system_prompt=None,
            error=None,
        )

        logger.debug(f"ThreadID: {thread_id}: Начальное состояние создано")

        logger.info(f"ThreadID: {thread_id}: Запуск выполнения графа...")

        final_state = graph.invoke(initial_state, config=config)

        logger.debug(f"ThreadID: {thread_id}: Получен final_state типа: {type(final_state).__name__}")

        if hasattr(final_state, 'final_result') and final_state.final_result:
            final_result = final_state.final_result
        elif hasattr(final_state, 'result') and final_state.result:
            final_result = final_state.result
        elif isinstance(final_state, dict) and final_state.get('final_result'):
            final_result = final_state['final_result']
        elif isinstance(final_state, dict) and final_state.get('result'):
            final_result = final_state['result']
        else:
            final_result = None

        agent_tokens = {}
        if hasattr(final_state, 'messages') and final_state.messages:
            for message in final_state.messages:
                if isinstance(message, AIMessage) and hasattr(message, 'usage_metadata') and message.usage_metadata:
                    tokens = message.usage_metadata.get("output_tokens", 0)
                    agent_tokens["final_agent"] = agent_tokens.get("final_agent", 0) + tokens

        if isinstance(final_state, GraphState):
            debug_final_state = _format_state_for_debug(final_state)
        elif isinstance(final_state, dict):
            debug_final_state = _format_state_for_debug(final_state)
        elif hasattr(final_state, '__dict__'):
            debug_final_state = _format_state_for_debug(final_state)
        else:
            debug_final_state = {"state": str(final_state), "type": type(final_state).__name__}

        result_data = {
            "thread_id": thread_id,
            "tokens_used": agent_tokens,
            "message_count": len(final_state.messages) if hasattr(final_state, 'messages') else 0,
            "final_state": debug_final_state
        }

        if final_result:
            logger.info(f"ThreadID: {thread_id}: Обработка завершена успешно. Длина результата: {len(final_result)}")
            result_data["result"] = final_result
            return result_data

        err_msg = None
        if hasattr(final_state, "error") and final_state.error:
            err_msg = final_state.error
        elif isinstance(final_state, dict) and final_state.get("error"):
            err_msg = final_state["error"]
        if err_msg:
            logger.warning(f"ThreadID: {thread_id}: Граф завершился с ошибкой: {err_msg}")
            result_data["error"] = err_msg
            return result_data

        logger.warning(f"ThreadID: {thread_id}: Результат не был сгенерирован")
        result_data["error"] = "No result generated"
        return result_data

    except Exception as e:
        logger.error(f"ThreadID: {thread_id if 'thread_id' in locals() else 'N/A'}: Критическая ошибка: {str(e)}")
        logger.exception("Трассировка стека:")

        return {
            "error": str(e),
            "thread_id": thread_id if 'thread_id' in locals() else None,
            "error_type": type(e).__name__
        }

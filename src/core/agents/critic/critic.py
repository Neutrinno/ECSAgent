import json
import re
from typing import Any, Dict, Literal, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from src.core.agents.critic.system_prompt import CRITIC_PROMPT
from src.core.graph_state import GraphState
from src.utils.logger import get_logger

logger = get_logger(__name__)

RETRY_LIMIT = 2

_VALID_ISSUE_TYPES = {"ok", "step_failed", "plan_failed", "need_clarify"}

_EXHAUSTED_MESSAGE = (
    "Не удалось подготовить полный ответ за отведённое число попыток. "
    "Попробуйте переформулировать запрос или уточнить параметры."
)


def _extract_json(text: str) -> Dict[str, Any]:
    """Извлекает JSON из ответа LLM — сначала напрямую, затем поиском блока."""
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


def _build_payload(state: GraphState) -> str:
    """Формирует JSON-контекст для LLM."""
    worker_results = {
        k: {
            "agent": v.agent,
            "task": v.task,
            "result": v.result,
            "status": v.status,
        }
        for k, v in state.step_results.items()
        if not k.startswith("_meta")
    }
    payload = {
        "user_query": state.user_query,
        "final_result": state.final_result,
        "plan_summary": state.plan_summary or "",
        "plan_steps": [s.model_dump() for s in state.plan_steps],
        "step_results": worker_results,
        "plan_risks": state.plan_risks,
        "retry_count": state.retry_count,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _fast_check(state: GraphState) -> Optional[Literal["step_failed", "need_clarify"]]:
    """
    Детерминированная быстрая проверка до LLM-вызова.
    Возвращает диагноз если ситуация однозначна, иначе None → идём в LLM.
    """
    # Нет финального ответа совсем
    if not state.final_result:
        failed = [
            k for k, v in state.step_results.items()
            if not k.startswith("_meta") and v.status == "failed"
        ]
        if failed:
            return "step_failed"
        return "need_clarify"

    # Есть явно failed шаги в step_results
    failed_steps = [
        k for k, v in state.step_results.items()
        if not k.startswith("_meta") and v.status == "failed"
    ]
    if failed_steps:
        return "step_failed"

    return None  # неоднозначно → решает LLM


class Critic:
    """Проверяет качество финального ответа и выносит диагноз.

    Логика двухуровневая:
    1. Быстрая детерминированная проверка (_fast_check) — покрывает очевидные случаи
       без LLM-вызова: нет final_result, есть failed шаги.
    2. LLM-проверка — для неочевидных случаев: релевантность, содержательность, достаточность.

    При исчерпании RETRY_LIMIT — честно сигнализирует через status="failed"
    и пишет понятное сообщение в final_result.

    Читает из state:  final_result, user_query, step_results, plan_steps,
                      plan_summary, plan_risks, retry_count.
    Пишет в state:    critic_issue_type, critic_feedback, failed_step_id,
                      status, retry_count, final_result (только при exhausted).
    """

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    def process_state(self, state: GraphState) -> Dict[str, Any]:
        """Точка входа ноды. Возвращает патч GraphState."""
        logger.debug("ThreadID: %s: Critic старт (retry_count=%d)", state.thread_id, state.retry_count)

        # Лимит исчерпан — честно завершаем с failed
        if state.retry_count >= RETRY_LIMIT:
            logger.warning(
                "ThreadID: %s: Critic retry_count=%d >= лимита %d, завершаем с failed",
                state.thread_id, state.retry_count, RETRY_LIMIT,
            )
            return {
                "critic_issue_type": "ok",      # останавливаем цикл роутера
                "critic_feedback": f"Лимит повторов ({RETRY_LIMIT}) исчерпан",
                "failed_step_id": None,
                "status": "failed",             # control_layer увидит → END
                "final_result": _EXHAUSTED_MESSAGE,
                "retry_count": state.retry_count,
            }

        issue_type, failed_step_id, feedback = self._diagnose(state)

        if issue_type == "ok":
            status = "ok"
            retry_count = state.retry_count
        else:
            status = "in_progress"
            retry_count = state.retry_count + 1

        logger.info(
            "ThreadID: %s: Critic диагноз=%s, failed_step=%s, retry=%d",
            state.thread_id, issue_type, failed_step_id, retry_count,
        )

        return {
            "critic_issue_type": issue_type,
            "critic_feedback": feedback,
            "failed_step_id": failed_step_id,
            "status": status,
            "retry_count": retry_count,
        }

    def _diagnose(
        self, state: GraphState
    ) -> tuple[str, Optional[str], str]:
        """
        Возвращает (issue_type, failed_step_id, feedback).
        Сначала быстрая проверка, затем LLM если нужно.
        """
        
        # Быстрая детерминированная проверка
        fast_result = _fast_check(state)
        if fast_result == "step_failed":
            failed_step_id = next(
                (k for k, v in state.step_results.items()
                 if not k.startswith("_meta") and v.status == "failed"),
                None,
            )
            return "step_failed", failed_step_id, f"Шаг {failed_step_id} завершился с ошибкой"

        if fast_result == "need_clarify":
            return "need_clarify", None, "Нет данных для формирования ответа"

        # LLM-проверка для неочевидных случаев
        return self._ask_llm(state)

    def _ask_llm(self, state: GraphState) -> tuple[str, Optional[str], str]:
        """Вызывает LLM для глубокой проверки релевантности и содержательности."""
        try:
            response = self.llm.invoke([
                SystemMessage(content=CRITIC_PROMPT.strip()),
                HumanMessage(content=_build_payload(state)),
            ])
            raw = response.content if isinstance(response.content, str) else str(response.content)
            parsed = _extract_json(raw)

            issue_type = str(parsed.get("issue_type", "ok")).strip()
            if issue_type not in _VALID_ISSUE_TYPES:
                logger.warning("Critic: неизвестный issue_type '%s', fallback → ok", issue_type)
                issue_type = "ok"

            failed_step_id = parsed.get("failed_step_id") or None
            if failed_step_id == "null":
                failed_step_id = None

            feedback = str(parsed.get("feedback", "")).strip()

            return issue_type, failed_step_id, feedback

        except Exception as e:
            logger.error("ThreadID: %s: Critic LLM ошибка: %s", state.thread_id, e, exc_info=True)
            return "ok", None, f"Ошибка проверки: {e}"

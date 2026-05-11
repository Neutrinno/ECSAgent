import json
from typing import Dict, Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from src.core.agents.aggregator.system_prompt import AGGREGATOR_PROMPT
from src.core.graph_state import GraphState, StepResult
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _get_current_plan_results(state: GraphState) -> Dict[str, StepResult]:
    """Возвращает только результаты шагов текущего плана (без stale и _meta)."""
    plan_step_map = {step.step_id: step for step in state.plan_steps if step.agent != "aggregator"}
    results: Dict[str, StepResult] = {}
    for step_id, result in state.step_results.items():
        if step_id.startswith("_meta"):
            continue
        step = plan_step_map.get(step_id)
        if not step:
            continue
        if result.agent != step.agent:
            continue
        results[step_id] = result
    return results


def _build_payload(state: GraphState, worker_results: Dict[str, StepResult]) -> str:
    """Формирует JSON-контекст для LLM."""
    payload = {
        "user_query": state.user_query,
        "plan_summary": state.plan_summary or "",
        "step_results": {
            k: {
                "agent": v.agent,
                "task": v.task,
                "result": v.result,
                "status": v.status,
            }
            for k, v in worker_results.items()
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class Aggregator:
    """Собирает результаты всех воркеров в единый финальный ответ пользователю.

    Читает из state:  step_results (только не-_meta слоты), plan_summary, user_query.
    Пишет в state:    final_result.
    """

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    def process_state(self, state: GraphState) -> Dict[str, Any]:
        """Точка входа ноды. Возвращает патч GraphState."""
        logger.debug("ThreadID: %s: Aggregator старт", state.thread_id)

        worker_results = _get_current_plan_results(state)

        # Нет ни одного результата — возвращаем заглушку без LLM-вызова
        if not worker_results:
            logger.warning("ThreadID: %s: Aggregator: нет результатов воркеров", state.thread_id)
            return {"final_result": "Не удалось получить данные для ответа. Уточните запрос."}

        try:
            response = self.llm.invoke([
                SystemMessage(content=AGGREGATOR_PROMPT.strip()),
                HumanMessage(content=_build_payload(state, worker_results)),
            ])
            final_result = str(response.content).strip()
        except Exception as e:
            logger.error("ThreadID: %s: Aggregator LLM ошибка: %s", state.thread_id, e, exc_info=True)
            # Fallback: склеиваем результаты воркеров напрямую
            final_result = "\n\n".join(
                v.result for v in worker_results.values()
                if v.result and v.status == "ok"
            ) or "Не удалось сформировать ответ."

        logger.info(
            "ThreadID: %s: Aggregator сформировал ответ (len=%d)",
            state.thread_id,
            len(final_result),
        )
        return {"final_result": final_result}
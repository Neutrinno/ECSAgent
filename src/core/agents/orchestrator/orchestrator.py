import json
import re
from typing import Any, Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from src.core.agents.orchestrator.system_prompt import ORCHESTRATOR_AGENT_PROMPT
from src.core.graph_state import GraphState, PlanStep, StepResult
from src.utils.logger import get_logger

logger = get_logger(__name__)

_ALLOWED_NEXT_AGENTS = {
    "sql_agent",
    "client_flow_agent",
    "network_optimizer_agent",
    "relocation_agent",
    "aggregator",
}


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


def _get_ready_steps(
    plan_steps: List[PlanStep],
    completed_steps: List[str],
) -> List[PlanStep]:
    """
    Возвращает шаги, готовые к запуску:
    - не выполнены (step_id не в completed_steps);
    - не aggregator (aggregator запускается отдельной логикой);
    - все depends_on уже выполнены.
    """
    completed = set(completed_steps)
    return [
        step for step in plan_steps
        if step.step_id not in completed
        and step.agent != "aggregator"
        and all(dep in completed for dep in step.depends_on)
    ]


def _all_worker_steps_done(
    plan_steps: List[PlanStep],
    completed_steps: List[str],
) -> bool:
    """Возвращает True если все шаги кроме aggregator выполнены."""
    completed = set(completed_steps)
    return all(
        step.step_id in completed
        for step in plan_steps
        if step.agent != "aggregator"
    )


def _build_payload(state: GraphState) -> str:
    """Формирует JSON-контекст для LLM."""
    payload = {
        "user_query": state.user_query,
        "plan_summary": state.plan_summary,
        "plan_steps": [step.model_dump() for step in state.plan_steps],
        "completed_steps": state.completed_steps,
        "failed_step_id": state.failed_step_id,
        "step_results": {
            k: {"agent": v.agent, "task": v.task, "status": v.status, "result": v.result}
            for k, v in state.step_results.items()
            if not k.startswith("_meta")
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class Orchestrator:
    """Определяет следующий шаг плана на каждой итерации.

    Логика выбора (детерминированная часть):
    1. step_failed retry → перезапустить failed_step_id.
    2. Есть готовые к запуску шаги → первый из них.
    3. Все шаги выполнены → aggregator.

    LLM используется как fallback когда детерминированная логика не даёт однозначного ответа.
    Это снижает количество LLM-вызовов на простых линейных планах.

    Читает из state:  plan_steps, completed_steps, failed_step_id, step_results, urf_codes.
    Пишет в state:    next_agent, current_step_id, completed_steps (убирает failed),
                      failed_step_id (сбрасывает после retry), step_results["_meta_orchestrator"].
    """

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    def process_state(self, state: GraphState) -> Dict[str, Any]:
        """Точка входа ноды. Возвращает патч GraphState."""
        logger.debug("ThreadID: %s: Orchestrator старт", state.thread_id)

        next_agent, current_step_id, reason = self._determine_next(state)

        # Обновляем completed_steps: убираем failed шаг чтобы он мог быть перезапущен
        completed_steps = list(state.completed_steps)
        failed_step_id = state.failed_step_id
        if failed_step_id and failed_step_id in completed_steps:
            completed_steps.remove(failed_step_id)

        logger.info(
            "ThreadID: %s: Orchestrator → %s (шаг: %s, причина: %s)",
            state.thread_id, next_agent, current_step_id, reason,
        )

        meta = StepResult(
            agent="orchestrator",
            task="Выбор следующего шага",
            result=f"next_agent={next_agent}, step={current_step_id}, reason={reason}",
            status="ok",
        )

        return {
            "next_agent": next_agent,
            "current_step_id": current_step_id,
            "completed_steps": completed_steps,
            "failed_step_id": None,  # сбрасываем после обработки
            "step_results": {**state.step_results, "_meta_orchestrator": meta},
        }

    def _determine_next(
        self, state: GraphState
    ) -> tuple[str, Optional[str], str]:
        """
        Возвращает (next_agent, current_step_id, reason).

        Сначала пробует детерминированную логику — она работает для большинства
        линейных планов без LLM-вызова. Только если план неоднозначен — идёт в LLM.
        """
        plan_steps = state.plan_steps
        completed_steps = state.completed_steps
        failed_step_id = state.failed_step_id

        # Пустой план → aggregator
        if not plan_steps:
            return "aggregator", None, "план пустой"

        # Retry конкретного шага
        if failed_step_id:
            step = next((s for s in plan_steps if s.step_id == failed_step_id), None)
            if step:
                return step.agent, step.step_id, f"retry шага {failed_step_id}"
            logger.warning("Orchestrator: failed_step_id=%s не найден в плане", failed_step_id)

        # Все воркеры выполнены → aggregator
        if _all_worker_steps_done(plan_steps, completed_steps):
            return "aggregator", None, "все шаги выполнены"

        # Готовые к запуску шаги
        ready = _get_ready_steps(plan_steps, completed_steps)
        if len(ready) == 1:
            # Один готовый шаг — детерминированный выбор
            return ready[0].agent, ready[0].step_id, f"следующий шаг по плану: {ready[0].step_id}"

        if len(ready) > 1:
            # Проверяем есть ли параллельная группа среди готовых шагов
            groups: dict[str, list] = {}
            for step in ready:
                if step.parallel_group:
                    groups.setdefault(step.parallel_group, []).append(step)

            for group_name, group_steps in groups.items():
                if len(group_steps) > 1:
                    # Сигнализируем роутеру: он сам найдёт готовые шаги и запустит Send.
                    # Роутер вызывает _get_ready_steps независимо и не смотрит на next_agent
                    # при наличии параллельной группы.
                    return "__parallel__", None, f"параллельная группа '{group_name}'"

            # Нет параллельной группы — берём первый готовый шаг
            step = ready[0]
            return step.agent, step.step_id, f"первый из {len(ready)} готовых шагов: {step.step_id}"

        # Нет готовых шагов и не все выполнены — нестандартная ситуация, идём в LLM
        logger.warning(
            "ThreadID: %s: Orchestrator: нет готовых шагов, запрашиваем LLM",
            state.thread_id,
        )
        return self._ask_llm(state)

    def _ask_llm(self, state: GraphState) -> tuple[str, Optional[str], str]:
        """Fallback: спрашиваем LLM когда детерминированная логика не справилась."""
        try:
            response = self.llm.invoke([
                SystemMessage(content=ORCHESTRATOR_AGENT_PROMPT.strip()),
                HumanMessage(content=_build_payload(state)),
            ])
            raw = response.content if isinstance(response.content, str) else str(response.content)
            parsed = _extract_json(raw)

            next_agent_raw = str(parsed.get("next_agent", "")).strip()
            next_agent = next_agent_raw if next_agent_raw in _ALLOWED_NEXT_AGENTS else "aggregator"
            reason = str(parsed.get("reason", "LLM fallback")).strip()

            # Пытаемся найти step_id для выбранного агента
            current_step_id = None
            for step in state.plan_steps:
                if step.agent == next_agent and step.step_id not in state.completed_steps:
                    current_step_id = step.step_id
                    break

            return next_agent, current_step_id, reason

        except Exception as e:
            logger.error("ThreadID: %s: Orchestrator LLM fallback ошибка: %s", state.thread_id, e)
            return "aggregator", None, f"ошибка LLM fallback: {e}"
            
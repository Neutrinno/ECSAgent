import json
import re
from typing import Any, Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from src.core.agents.planner_agent.system_prompt import PLANNER_AGENT_PROMPT
from src.core.graph_state import GraphState, PlanStep, StepResult
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Агенты, которые планировщик может включать в план
_ALLOWED_AGENTS = {
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
        raise ValueError(f"Planner: JSON не найден в ответе модели: {cleaned[:200]}")
    return json.loads(match.group(0))


def _parse_plan_steps(raw: Any) -> List[PlanStep]:
    """
    Преобразует сырой список шагов из JSON в List[PlanStep].
    Пропускает шаги с недопустимым агентом (кроме aggregator).
    """
    if not isinstance(raw, list):
        return []

    steps: List[PlanStep] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        agent = str(item.get("agent", "")).strip()
        if agent not in _ALLOWED_AGENTS:
            logger.warning("Planner: пропущен шаг с недопустимым агентом '%s'", agent)
            continue
        steps.append(PlanStep(
            step_id=str(item.get("step_id", f"step_{len(steps) + 1}")),
            agent=agent,
            task=str(item.get("task", "")).strip(),
            depends_on=[str(d) for d in item.get("depends_on", []) if d],
            parallel_group=item.get("parallel_group") or None,
        ))
    return steps


def _parse_risks(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    return [str(r).strip() for r in raw if str(r).strip()]


def _build_user_payload(state: GraphState) -> str:
    """Формирует текст запроса для LLM с учётом контекста перепланирования."""
    parts = [f"Запрос пользователя: {state.user_query}"]

    if state.urf_codes:
        parts.append(f"Найденные urf_codes: {', '.join(state.urf_codes)}")

    # Контекст перепланирования — передаём критику фидбек и старый план
    if state.critic_issue_type == "plan_failed" and state.critic_feedback:
        parts.append(f"\nПредыдущий план не сработал. Замечания критика:\n{state.critic_feedback}")
        if state.plan_summary:
            parts.append(f"Предыдущая стратегия: {state.plan_summary}")

    return "\n".join(parts)


class PlannerAgent:
    """Формирует структурированный план выполнения запроса для Orchestrator.

    Читает из state: user_query, urf_codes, critic_feedback (при replan).
    Пишет в state: plan_steps, plan_summary, plan_risks, step_results["_meta_plan"].
    """

    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self._structured = self._try_structured_output()

    def _try_structured_output(self):
        """Пробует подключить structured output; при неудаче вернёт None → JSON fallback."""
        try:
            from pydantic import BaseModel, Field

            class _PlanSchema(BaseModel):
                plan_summary: str = Field(description="Краткая стратегия выполнения")
                plan_steps: List[Dict[str, Any]] = Field(description="Шаги плана")
                plan_risks: List[str] = Field(default_factory=list)

            from langchain_core.prompts import ChatPromptTemplate
            prompt = ChatPromptTemplate.from_messages([
                ("system", PLANNER_AGENT_PROMPT.strip()),
                ("human", "{user_content}"),
            ])
            return prompt | self.llm.with_structured_output(_PlanSchema)
        except Exception as e:
            logger.warning("Planner: structured_output недоступен (%s), используем JSON fallback", e)
            return None

    def _invoke_llm(self, user_content: str) -> Dict[str, Any]:
        """Вызывает LLM — через structured output или JSON fallback."""
        if self._structured is not None:
            try:
                result = self._structured.invoke({"user_content": user_content})
                return result.model_dump() if hasattr(result, "model_dump") else dict(result)
            except Exception as e:
                logger.warning("Planner: structured_output не сработал (%s), fallback", e)

        response = self.llm.invoke([
            SystemMessage(content=PLANNER_AGENT_PROMPT.strip()),
            HumanMessage(content=user_content),
        ])
        raw = response.content if isinstance(response.content, str) else str(response.content)
        return _extract_json(raw)

    def process_state(self, state: GraphState) -> Dict[str, Any]:
        """Точка входа ноды. Возвращает патч GraphState."""
        logger.debug("ThreadID: %s: PlannerAgent старт", state.thread_id)

        try:
            user_content = _build_user_payload(state)
            parsed = self._invoke_llm(user_content)

            plan_steps = _parse_plan_steps(parsed.get("plan_steps", []))
            plan_summary = str(parsed.get("plan_summary", "")).strip() or "План сформирован"
            plan_risks = _parse_risks(parsed.get("plan_risks", []))

            # Fallback: если план пустой или не содержит воркеров — создаём минимальный план
            if not plan_steps:
                logger.warning("Planner: пустой план, применяем fallback")
                plan_steps = [
                    PlanStep(step_id="step_1", agent="sql_agent",
                             task=state.user_query, depends_on=[]),
                    PlanStep(step_id="step_2", agent="aggregator",
                             task="Сформировать итоговый ответ", depends_on=["step_1"]),
                ]

            logger.info(
                "ThreadID: %s: Planner сформировал план из %d шагов: %s",
                state.thread_id,
                len(plan_steps),
                [f"{s.step_id}:{s.agent}" for s in plan_steps],
            )

            meta: StepResult = StepResult(
                agent="planner_agent",
                task="Формирование плана",
                result=plan_summary,
                status="ok",
            )

            return {
                "plan_steps": plan_steps,
                "plan_summary": plan_summary,
                "plan_risks": plan_risks,
                # Сбрасываем прогресс оркестратора при (пере)планировании
                "completed_steps": [],
                "current_step_id": None,
                "next_agent": None,
                # Сбрасываем диагноз критика — новый план начинается чисто
                "critic_issue_type": None,
                "critic_feedback": None,
                "failed_step_id": None,
                # Служебная запись
                "step_results": {**state.step_results, "_meta_plan": meta},
            }

        except Exception as e:
            logger.error("ThreadID: %s: PlannerAgent ошибка: %s", state.thread_id, e, exc_info=True)
            meta_err: StepResult = StepResult(
                agent="planner_agent",
                task="Формирование плана",
                result=str(e),
                status="failed",
            )
            return {
                "error": f"PlannerAgent error: {e}",
                "status": "failed",
                "step_results": {**state.step_results, "_meta_plan": meta_err},
            }
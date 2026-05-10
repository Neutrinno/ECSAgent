from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    """Один шаг плана с явными зависимостями между шагами.

    Поле depends_on позволяет коду (оркестратору) определить порядок запуска
    без участия LLM: если depends_on пустой — шаг можно запустить сразу,
    если содержит step_id — нужно дождаться результата этого шага.

    Поле parallel_group позволяет запускать несколько независимых шагов
    одновременно (активируется позже через LangGraph Send).
    """

    step_id: str                                        # "step_1", "step_2", ...
    agent: str                                          # целевой агент
    task: str                                           # задача на естественном языке
    depends_on: List[str] = Field(default_factory=list) # [] → запустить сразу
                                                        # ["step_1"] → ждёт step_1
    parallel_group: Optional[str] = None                # "group_a" → запустить параллельно с группой


class StepResult(BaseModel):
    """Результат одного выполненного шага.

    Соглашение по ключам в GraphState.step_results:
      - "step_N"          — результат воркера (sql_agent, client_flow_agent, ...)
      - "_meta_plan"      — служебные данные от planner_agent
      - "_meta_orchestrator" — лог решений оркестратора (для отладки)

    Агрегатор и критик работают только с ключами без префикса "_meta".
    """

    agent: str
    task: str
    result: Optional[str] = None
    tools_called: List[Dict[str, Any]] = Field(default_factory=list)  # инструменты и их аргументы
    status: Literal["pending", "ok", "failed"] = "pending"


class GraphState(BaseModel):
    """Единое состояние графа.

    Каждый агент читает и пишет только поля из своего контракта (см. спецификацию §4).
    Данные не сбрасываются при retry/replan — агенты работают с накопленным контекстом.
    """

    # ── Вход ──────────────────────────────────────────────────────────────
    user_query: str                                             # оригинальный запрос пользователя
    messages: List[BaseMessage] = Field(default_factory=list)  # история диалога
    thread_id: Optional[UUID] = None

    # ── Идентификация ВСП ─────────────────────────────────────────────────
    urf_codes: List[str] = Field(default_factory=list)

    # ── Control layer ─────────────────────────────────────────────────────
    control_layer_answer: Optional[str] = None  # прямой ответ без запуска пайплайна

    # ── План ──────────────────────────────────────────────────────────────
    plan_steps: List[PlanStep] = Field(default_factory=list)
    plan_summary: Optional[str] = None
    plan_risks: List[str] = Field(default_factory=list)

    # ── Прогресс оркестратора ─────────────────────────────────────────────
    completed_steps: List[str] = Field(default_factory=list)  # ["step_1", "step_2", ...]
    current_step_id: Optional[str] = None                     # шаг, выполняемый прямо сейчас
    next_agent: Optional[str] = None                          # для роутера route_from_orchestrator

    # ── Результаты агентов ────────────────────────────────────────────────
    # Воркеры пишут в "step_N", служебные агенты — в "_meta_*"
    # Агрегатор фильтрует: {k: v for k, v in step_results.items() if not k.startswith("_meta")}
    step_results: Dict[str, StepResult] = Field(default_factory=dict)

    # ── Финальный ответ ───────────────────────────────────────────────────
    final_result: Optional[str] = None

    # ── Диагностика критика ───────────────────────────────────────────────
    critic_issue_type: Optional[Literal[
        "ok",           # всё хорошо → control_layer завершает
        "plan_failed",  # неверный план → control_layer → planner_agent
        "step_failed",  # плохой шаг → control_layer → orchestrator
        "need_clarify", # недостаточно данных → control_layer → пользователь
    ]] = None
    critic_feedback: Optional[str] = None   # пометки для следующего агента
    failed_step_id: Optional[str] = None    # при step_failed: какой шаг перезапустить

    # ── Служебные ─────────────────────────────────────────────────────────
    status: Literal["in_progress", "ok", "failed"] = "in_progress"
    retry_count: int = 0
    error: Optional[str] = None
    
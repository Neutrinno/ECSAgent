from typing import Annotated, Any, Dict, List, Literal, Optional
from uuid import UUID

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


# ── Reducer-функции ───────────────────────────────────────────────────────────

def _merge_step_results(left: Dict, right: Dict) -> Dict:
    """Сливает результаты параллельных воркеров.

    При последовательном исполнении right содержит один новый ключ —
    поведение идентично обычному присваиванию.
    При параллельном (Send) — два воркера пишут одновременно,
    reducer объединяет оба словаря без потерь.
    """
    return {**left, **right}


def _merge_completed_steps(left: List[str], right: List[str]) -> List[str]:
    """Объединяет списки выполненных шагов без дублей, сохраняя порядок.

    При параллельном исполнении оба воркера добавляют свой step_id —
    reducer гарантирует что оба попадут в список.
    """
    return list(dict.fromkeys(left + right))


# ── Вспомогательные модели ────────────────────────────────────────────────────

class PlanStep(BaseModel):
    """Один шаг плана с явными зависимостями между шагами.

    depends_on: [] → шаг готов сразу; ["step_1"] → ждёт результат step_1.
    parallel_group: одинаковая строка у нескольких шагов → запускать через Send.
    """

    step_id: str                                        # "step_1", "step_2", ...
    agent: str                                          # целевой агент
    task: str                                           # задача на естественном языке
    depends_on: List[str] = Field(default_factory=list)
    parallel_group: Optional[str] = None


class StepResult(BaseModel):
    """Результат одного выполненного шага.

    Соглашение по ключам в GraphState.step_results:
      "step_N"              — результат воркера (sql_agent, client_flow_agent, ...)
      "_meta_plan"          — служебные данные от planner_agent
      "_meta_orchestrator"  — лог решений оркестратора (для отладки)

    Агрегатор и критик работают только с ключами без префикса "_meta".
    """

    agent: str
    task: str
    result: Optional[str] = None
    tools_called: List[Dict[str, Any]] = Field(default_factory=list)
    status: Literal["pending", "ok", "failed"] = "pending"


# ── GraphState ────────────────────────────────────────────────────────────────

class GraphState(BaseModel):
    """Единое состояние графа.

    Каждый агент читает и пишет только поля из своего контракта.
    Данные не сбрасываются при retry/replan — агенты работают с накопленным контекстом.

    Поля с Annotated[..., reducer] поддерживают параллельный запуск через LangGraph Send:
    при одновременной записи нескольких нод reducer объединяет результаты корректно.
    """

    # ── Вход ──────────────────────────────────────────────────────────────
    user_query: str
    messages: List[BaseMessage] = Field(default_factory=list)
    thread_id: Optional[UUID] = None

    # ── Идентификация ВСП ─────────────────────────────────────────────────
    urf_codes: List[str] = Field(default_factory=list)

    # ── Control layer ─────────────────────────────────────────────────────
    control_layer_answer: Optional[str] = None

    # ── План ──────────────────────────────────────────────────────────────
    plan_steps: List[PlanStep] = Field(default_factory=list)
    plan_summary: Optional[str] = None
    plan_risks: List[str] = Field(default_factory=list)

    # ── Прогресс оркестратора ─────────────────────────────────────────────
    # Annotated + reducer: при параллельном Send несколько воркеров добавляют
    # свой step_id одновременно — без reducer второй затрёт первый.
    completed_steps: Annotated[List[str], _merge_completed_steps] = Field(default_factory=list)
    current_step_id: Optional[str] = None
    next_agent: Optional[str] = None

    # ── Результаты агентов ────────────────────────────────────────────────
    # Annotated + reducer: при параллельном Send два воркера пишут в разные
    # ключи одновременно — без reducer второй патч затрёт результат первого.
    # Воркеры пишут в "step_N", служебные агенты — в "_meta_*".
    # Агрегатор фильтрует: {k: v for k, v in step_results.items() if not k.startswith("_meta")}
    step_results: Annotated[Dict[str, StepResult], _merge_step_results] = Field(
        default_factory=dict
    )

    # ── Финальный ответ ───────────────────────────────────────────────────
    final_result: Optional[str] = None

    # ── Диагностика критика ───────────────────────────────────────────────
    critic_issue_type: Optional[Literal[
        "ok",           # всё хорошо → control_layer завершает
        "plan_failed",  # неверный план → control_layer → planner_agent
        "step_failed",  # плохой шаг → control_layer → orchestrator
        "need_clarify", # недостаточно данных → control_layer → пользователь
    ]] = None
    critic_feedback: Optional[str] = None
    failed_step_id: Optional[str] = None

    # ── Служебные ─────────────────────────────────────────────────────────
    status: Literal["in_progress", "ok", "failed"] = "in_progress"
    retry_count: int = 0
    error: Optional[str] = None
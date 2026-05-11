from typing import List, Union

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Send

from src.core.graph_state import GraphState, PlanStep
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Допустимые цели маршрутизации из оркестратора
_WORKER_AGENTS = {
    "sql_agent",
    "client_flow_agent",
    "network_optimizer_agent",
    "relocation_agent",
}
_ALLOWED_NEXT_AGENTS = _WORKER_AGENTS | {"aggregator"}


# =========================
# HELPERS
# =========================

def _get_state_attr(state: GraphState | dict, name: str):
    if isinstance(state, dict):
        return state.get(name)
    return getattr(state, name, None)


def _get_ready_steps(
    plan_steps: List[PlanStep],
    completed_steps: List[str],
) -> List[PlanStep]:
    """Возвращает шаги готовые к запуску: не выполнены, не aggregator,
    все зависимости выполнены."""
    completed = set(completed_steps)
    return [
        step for step in plan_steps
        if step.step_id not in completed
        and step.agent != "aggregator"
        and all(dep in completed for dep in step.depends_on)
    ]


# =========================
# ROUTERS
# =========================

def route_from_control(state: GraphState | dict) -> str:
    """Роутинг из control_layer.

    Логика (в порядке приоритета):
    1. Прямой ответ без пайплайна — завершаем.
    2. Терминальный статус (ok / failed) — завершаем.
    3. После критика — маршрут по типу проблемы:
       - plan_failed  → planner_agent
       - step_failed  → orchestrator
       - need_clarify → end (control_layer уже задал вопрос пользователю)
       - ok           → end
    4. Первый вход — старт пайплайна → planner_agent.
    """
    tid = _get_state_attr(state, "thread_id")
    control_answer = _get_state_attr(state, "control_layer_answer")
    critic_issue_type = _get_state_attr(state, "critic_issue_type")
    status = _get_state_attr(state, "status")

    # Прямой ответ без пайплайна
    if control_answer and not critic_issue_type:
        logger.info("ThreadID: %s: direct answer from control_layer, завершаем", tid)
        return "end"

    # Терминальные статусы
    if status in ("ok", "failed"):
        logger.info("ThreadID: %s: терминальный статус %s", tid, status)
        return "end"

    # После критика — маршрут по диагнозу
    if critic_issue_type:
        match critic_issue_type:
            case "plan_failed":
                logger.info("ThreadID: %s: critic plan_failed → planner_agent", tid)
                return "planner_agent"
            case "step_failed":
                logger.info("ThreadID: %s: critic step_failed → orchestrator", tid)
                return "orchestrator"
            case "need_clarify":
                logger.info("ThreadID: %s: critic need_clarify → end", tid)
                return "end"
            case "ok":
                logger.info("ThreadID: %s: critic ok → end", tid)
                return "end"

    # Первый вход — старт пайплайна
    logger.info("ThreadID: %s: старт пайплайна → planner_agent", tid)
    return "planner_agent"


def route_from_orchestrator(
    state: GraphState | dict,
) -> Union[str, List[Send]]:
    """Роутинг из orchestrator.

    При одном готовом шаге — возвращает строку (обычный маршрут).
    При нескольких шагах одной parallel_group — возвращает List[Send]
    для параллельного запуска через LangGraph Send.
    Fallback при любой неопределённости — aggregator.
    """
    tid = _get_state_attr(state, "thread_id")
    next_agent = _get_state_attr(state, "next_agent")
    plan_steps = _get_state_attr(state, "plan_steps") or []
    completed_steps = _get_state_attr(state, "completed_steps") or []

    # Проверяем готовые шаги для параллельного запуска
    ready = _get_ready_steps(plan_steps, completed_steps)

    if len(ready) > 1:
        # Группируем по parallel_group
        grouped: dict[str, List[PlanStep]] = {}
        for step in ready:
            if step.parallel_group:
                grouped.setdefault(step.parallel_group, []).append(step)

        # Если есть группа из 2+ шагов — запускаем параллельно
        for group_name, group_steps in grouped.items():
            if len(group_steps) > 1:
                state_dict = (
                    state.model_dump() if hasattr(state, "model_dump") else dict(state)
                )
                logger.info(
                    "ThreadID: %s: параллельный запуск %d шагов группы '%s': %s",
                    tid, len(group_steps), group_name,
                    [s.step_id for s in group_steps],
                )
                return [
                    Send(step.agent, {**state_dict, "current_step_id": step.step_id})
                    for step in group_steps
                ]

    # Обычный маршрут — один шаг
    # "__parallel__" не попадает в allowed — роутер уже обработал параллельный случай выше
    if next_agent in _ALLOWED_NEXT_AGENTS:
        logger.info("ThreadID: %s: orchestrator → %s", tid, next_agent)
        return next_agent

    logger.info(
        "ThreadID: %s: orchestrator fallback → aggregator (next_agent=%s)", tid, next_agent
    )
    return "aggregator"


# =========================
# GRAPH
# =========================

class AgentGraph:
    """Граф мультиагентной системы с паттерном supervisor.

    Поток управления:
        control_layer → planner_agent → orchestrator ⇄ воркеры → aggregator → critic → control_layer

    Роутеры:
        route_from_control      — старт / прямой ответ / replan / retry / end после критика
        route_from_orchestrator — один воркер (str) или параллельный запуск (List[Send])

    Критик всегда возвращает управление в control_layer (жёсткое ребро).
    Вся логика разветвления после критика живёт в route_from_control.
    """

    def __init__(
        self,
        control_layer,
        planner_agent,
        orchestrator,
        sql_agent,
        client_flow_agent,
        network_optimizer_agent,
        relocation_agent,
        aggregator,
        critic,
    ):
        # Supervisor
        self.control_layer = control_layer

        # Планирование и оркестрация
        self.planner_agent = planner_agent
        self.orchestrator = orchestrator

        # Специализированные агенты (воркеры)
        self.sql_agent = sql_agent
        self.client_flow_agent = client_flow_agent
        self.network_optimizer_agent = network_optimizer_agent
        self.relocation_agent = relocation_agent

        # Постобработка
        self.aggregator = aggregator
        self.critic = critic

        self.memory = MemorySaver()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(GraphState)

        # ── Ноды ──────────────────────────────────────────────────────────
        workflow.add_node("control_layer", self.control_layer.process_state)
        workflow.add_node("planner_agent", self.planner_agent.process_state)
        workflow.add_node("orchestrator", self.orchestrator.process_state)

        workflow.add_node("sql_agent", self.sql_agent.process_state)
        workflow.add_node("client_flow_agent", self.client_flow_agent.process_state)
        workflow.add_node("network_optimizer_agent", self.network_optimizer_agent.process_state)
        workflow.add_node("relocation_agent", self.relocation_agent.process_state)

        workflow.add_node("aggregator", self.aggregator.process_state)
        workflow.add_node("critic", self.critic.process_state)

        # ── Точка входа ───────────────────────────────────────────────────
        workflow.set_entry_point("control_layer")

        # ── control_layer → условный переход ──────────────────────────────
        workflow.add_conditional_edges(
            "control_layer",
            route_from_control,
            {
                "planner_agent": "planner_agent",
                "orchestrator": "orchestrator",
                "end": END,
            },
        )

        # ── Основной поток ────────────────────────────────────────────────
        workflow.add_edge("planner_agent", "orchestrator")

        # route_from_orchestrator возвращает str (один шаг) или List[Send] (параллельно).
        # LangGraph обрабатывает Send автоматически — явного ключа в маппинге не нужно.
        workflow.add_conditional_edges(
            "orchestrator",
            route_from_orchestrator,
            {
                "sql_agent": "sql_agent",
                "client_flow_agent": "client_flow_agent",
                "network_optimizer_agent": "network_optimizer_agent",
                "relocation_agent": "relocation_agent",
                "aggregator": "aggregator",
            },
        )

        # ── Воркеры → оркестратор ─────────────────────────────────────────
        workflow.add_edge("sql_agent", "orchestrator")
        workflow.add_edge("client_flow_agent", "orchestrator")
        workflow.add_edge("network_optimizer_agent", "orchestrator")
        workflow.add_edge("relocation_agent", "orchestrator")

        # ── Финальные стадии ──────────────────────────────────────────────
        workflow.add_edge("aggregator", "critic")

        # Критик → control_layer: жёсткое ребро.
        # Разветвление по critic_issue_type происходит в route_from_control.
        workflow.add_edge("critic", "control_layer")

        return workflow.compile(checkpointer=self.memory)
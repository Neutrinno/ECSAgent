from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.core.graph_state import GraphState
from src.utils.logger import get_logger

logger = get_logger(__name__)


# =========================
# HELPERS
# =========================

def _get_state_attr(state: GraphState | dict, name: str):
    if isinstance(state, dict):
        return state.get(name)
    return getattr(state, name, None)


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


def route_from_orchestrator(state: GraphState | dict) -> str:
    """Оркестратор выбирает следующий шаг плана.

    Возвращает имя следующего агента из фиксированного списка допустимых целей.
    При неизвестном значении next_agent — fallback на aggregator.
    """
    tid = _get_state_attr(state, "thread_id")
    next_agent = _get_state_attr(state, "next_agent")

    allowed = {
        "sql_agent",
        "client_flow_agent",
        "network_optimizer_agent",
        "relocation_agent",
        "aggregator",
    }
    if next_agent in allowed:
        logger.info("ThreadID: %s: orchestrator → %s", tid, next_agent)
        return next_agent

    logger.info("ThreadID: %s: orchestrator fallback → aggregator (next_agent=%s)", tid, next_agent)
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
        route_from_orchestrator — выбор следующего воркера или aggregator

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
        # Покрывает: старт пайплайна / прямой ответ /
        #            replan (plan_failed) / retry (step_failed) / end
        workflow.add_conditional_edges(
            "control_layer",
            route_from_control,
            {
                "planner_agent": "planner_agent",
                "orchestrator": "orchestrator",  # step_failed: retry конкретного шага
                "end": END,
            },
        )

        # ── Основной поток ────────────────────────────────────────────────
        workflow.add_edge("planner_agent", "orchestrator")

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

        # Критик → control_layer: жёсткое ребро (не условный переход).
        # Разветвление по critic_issue_type происходит внутри route_from_control.
        workflow.add_edge("critic", "control_layer")

        return workflow.compile(checkpointer=self.memory)
        
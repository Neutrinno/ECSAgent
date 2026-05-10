from typing import Optional
import threading

from src.database.service import SQLiteService
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ServiceManager:
    """
    Singleton-менеджер для управления жизненным циклом сервисов.
    Инициализирует компоненты один раз и переиспользует их между запросами.
    """
    _instance: Optional['ServiceManager'] = None
    _initialized: bool = False
    _lock: threading.Lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._db_service: Optional[SQLiteService] = None
        self._llm = None
        self._planner_agent = None
        self._control_layer = None
        self._orchestrator = None
        self._aggregator = None
        self._critic = None
        self._network_optimizer_agent = None
        self._relocation_agent = None
        self._sql_agent = None
        self._client_flow_agent = None
        self._agent_graph = None

        logger.info("ServiceManager создан (еще не инициализирован)")

    def initialize(self):
        """
        Инициализация всех сервисов.
        Вызывается один раз при старте приложения.
        """
        if self._initialized:
            logger.debug("ServiceManager уже инициализирован, пропускаем")
            return

        with self._lock:         # Блокировка нужна, т.к. Streamlit может дергать инициализацию параллельно
            if self._initialized:
                logger.debug("ServiceManager уже инициализирован (после блокировки), пропускаем")
                return

            try:
                logger.info("Начинаем инициализацию ServiceManager...")

                logger.debug("Инициализация SQLiteService...")
                self._db_service = SQLiteService()
                logger.info("SQLiteService инициализирован")

                logger.debug("Инициализация LLM...")
                from src.core.llm_utils.llm_factory import llm
                self._llm = llm
                logger.info("LLM инициализирован")

                logger.debug("Инициализация агентов...")
                from src.core.agents.planner_agent.planner_agent import PlannerAgent
                from src.core.agents.control_layer.control_layer import ControlLayer
                from src.core.agents.orchestrator.orchestrator import Orchestrator
                from src.core.agents.aggregator.aggregator import Aggregator
                from src.core.agents.critic.critic import Critic
                from src.core.agents.network_optimizer_agent.network_optimizer_agent import NetworkOptimizerAgent
                from src.core.agents.relocation_agent.relocation_agent import RelocationAgent
                from src.core.agents.sql_agent.sql_agent import SQLAgent
                from src.core.agents.clientflow_agent.client_flow_agent import ClientFlowAgent

                self._control_layer = ControlLayer(llm=self._llm)
                self._planner_agent = PlannerAgent(llm=self._llm)
                self._orchestrator = Orchestrator(llm=self._llm)
                self._aggregator = Aggregator(llm=self._llm)
                self._critic = Critic(llm=self._llm)
                self._network_optimizer_agent = NetworkOptimizerAgent(llm=self._llm)
                self._relocation_agent = RelocationAgent(llm=self._llm)
                self._sql_agent = SQLAgent(llm=self._llm)
                self._client_flow_agent = ClientFlowAgent(llm=self._llm)

                logger.info("Агенты инициализированы")

                logger.debug("Инициализация графа агентов...")
                from src.core.graph import AgentGraph
                self._agent_graph = AgentGraph(
                    control_layer=self._control_layer,
                    planner_agent=self._planner_agent,
                    orchestrator=self._orchestrator,
                    network_optimizer_agent=self._network_optimizer_agent,
                    sql_agent=self._sql_agent,
                    client_flow_agent=self._client_flow_agent,
                    relocation_agent=self._relocation_agent,
                    aggregator=self._aggregator,
                    critic=self._critic,
                ).graph
                logger.info("Граф агентов инициализирован")

                self._initialized = True
                logger.info("✅ ServiceManager полностью инициализирован")

            except Exception as e:
                logger.error(f"Ошибка при инициализации ServiceManager: {str(e)}")
                logger.exception("Трассировка стека:")
                raise

    @property
    def db_service(self) -> SQLiteService:
        """Возвращает экземпляр SQLiteService"""
        if not self._initialized:
            self.initialize()
        return self._db_service

    @property
    def llm(self):
        """Возвращает экземпляр LLM"""
        if not self._initialized:
            self.initialize()
        return self._llm

    @property
    def planner_agent(self):
        """Возвращает экземпляр PlannerAgent"""
        if not self._initialized:
            self.initialize()
        return self._planner_agent

    @property
    def network_optimizer_agent(self):
        """Возвращает экземпляр NetworkOptimizerAgent"""
        if not self._initialized:
            self.initialize()
        return self._network_optimizer_agent

    @property
    def sql_agent(self):
        """Возвращает экземпляр SQLAgent"""
        if not self._initialized:
            self.initialize()
        return self._sql_agent

    @property
    def client_flow_agent(self):
        """Возвращает экземплярClientFlowAgent"""
        if not self._initialized:
            self.initialize()
        return self._client_flow_agent

    @property
    def agent_graph(self):
        """Возвращает скомпилированный граф агентов"""
        if not self._initialized:
            self.initialize()
        return self._agent_graph

    @property
    def is_initialized(self) -> bool:
        """Проверяет, инициализирован ли менеджер"""
        return self._initialized


service_manager = ServiceManager()

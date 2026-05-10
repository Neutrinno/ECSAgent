from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from langgraph.errors import ParentCommand
from typing import Dict, Any

from src.core.agents.sql_agent.prompt import SQL_AGENT_PROMPT
from src.core.agents.sql_agent.tools import (
    get_table_schema,
    execute_sql_query,
    list_tables_with_descriptions,
)
from src.core.graph_state import GraphState
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SQLAgent:
    """
    Агент, который извлекает данные из БД. Он отвечает за:
    1. Создание sql запросу по вопросу пользователя
    2. Реализацию sql запроса из базы данных
    3. Анализирует корректность полученных данных
    4. Отвечает на вопрос пользователя
    """

    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self.tools = [
            list_tables_with_descriptions,
            get_table_schema,
            execute_sql_query,
        ]
        self.tools_description = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])

        self.prompt = SQL_AGENT_PROMPT.format(tools_description=self.tools_description)
        self.agent = create_react_agent(model=self.llm,
                                        tools=self.tools,
                                        prompt=self.prompt)

    def process_state(self, state: GraphState) -> Dict[str, Any]:
        """
        Основной метод обработки состояния графа.
        Вызывается из LangGraph как нода.
        """
        try:
            if not state.user_query and not state.messages:
                raise ValueError("No query or messages provided")

            logger.info(f"ThreadID: {state.thread_id}: Starting SQL agent")
            messages = state.messages if state.messages else [HumanMessage(content=state.user_query)]
            resp = self.agent.invoke({"messages": messages})

            return {
                "messages": resp["messages"],
                "result": resp["messages"][-1].content if resp["messages"] else ""
            }

        except ParentCommand:
            logger.info(f"ThreadID: {state.thread_id}: SQL agent completed, transitioning to analyst")
            raise
        except Exception as e:
            logger.error(f"ThreadID: {state.thread_id}: SQL agent error: {str(e)}")
            return {
                "error": str(e),
                "agent_type": "sql_agent",
                "error_type": type(e).__name__
            }

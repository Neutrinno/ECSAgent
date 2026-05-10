from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.prebuilt import create_react_agent
from langgraph.errors import ParentCommand
from typing import Dict, Any
from datetime import date

from src.core.agents.clientflow_agent.system_prompt import CLIENT_FLOW_PROMPT
from src.core.agents.sql_agent.tools import get_table_schema, execute_sql_query

from src.core.graph_state import GraphState
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ClientFlowAgent:
    """
    Агент для анализа запроса клиентопотока по историческим данным
    """

    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self.tools = [
            get_table_schema,
            execute_sql_query,
        ]
        self.tools_description = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])

        self.prompt = CLIENT_FLOW_PROMPT.format(
            tools_description=self.tools_description,
            date=date.today().isoformat(),
        )
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

            logger.info(f"ThreadID: {state.thread_id}: Starting ClientFlow agent")
            if state.user_query:
                logger.info(f"ThreadID: {state.thread_id}: ClientFlow input query: {state.user_query}")
            messages = state.messages if state.messages else [HumanMessage(content=state.user_query)]
            input_count = len(messages)
            logger.info(f"ThreadID: {state.thread_id}: ClientFlow stage=invoke, input_messages={input_count}")
            resp = self.agent.invoke({"messages": messages})
            output_messages = resp.get("messages", [])
            logger.info(f"ThreadID: {state.thread_id}: ClientFlow stage=received, output_messages={len(output_messages)}")

            for msg in output_messages[input_count:]:
                if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                    for tc in msg.tool_calls:
                        tool_name = tc.get("name", "unknown")
                        tool_args = tc.get("args", {})
                        if isinstance(tool_args, dict) and "sql_query" in tool_args:
                            query_preview = " ".join(str(tool_args["sql_query"]).split())
                            if len(query_preview) > 300:
                                query_preview = query_preview[:300] + "..."
                            logger.info(
                                f"ThreadID: {state.thread_id}: ClientFlow tool_call={tool_name}, sql={query_preview}"
                            )
                            continue
                        logger.info(
                            f"ThreadID: {state.thread_id}: ClientFlow tool_call={tool_name}, args={tool_args}"
                        )
                elif isinstance(msg, ToolMessage):
                    tool_name = getattr(msg, "name", "unknown")
                    tool_result = str(msg.content or "")
                    if len(tool_result) > 300:
                        tool_result = tool_result[:300] + "..."
                    logger.info(
                        f"ThreadID: {state.thread_id}: ClientFlow tool_result={tool_name}, content={tool_result}"
                    )

            final_text = resp["messages"][-1].content if resp["messages"] else ""
            logger.info(
                f"ThreadID: {state.thread_id}: ClientFlow stage=finish, final_result_len={len(str(final_text))}"
            )

            return {
                "messages": resp["messages"],
                "result": final_text
            }

        except ParentCommand:
            logger.info(f"ThreadID: {state.thread_id}: ClientFlow agent completed, transitioning to analyst")
            raise
        except Exception as e:
            logger.error(f"ThreadID: {state.thread_id}: ClientFlow agent error: {str(e)}")
            return {
                "error": str(e),
                "agent_type": "client_flow_agent",
                "error_type": type(e).__name__
            }

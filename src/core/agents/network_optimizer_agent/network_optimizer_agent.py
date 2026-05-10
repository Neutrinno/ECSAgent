from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from langgraph.errors import ParentCommand
from typing import Dict, Any

from src.core.agents.network_optimizer_agent.network_optimizer_tools import (
    calculate_vsp_closure,
    calculate_vsp_relocation,
    get_vsp_info
)
from src.core.agents.network_optimizer_agent.system_prompt import NETWORK_OPTIMIZER_PROMPT
from src.core.graph_state import GraphState
from src.utils.logger import get_logger

logger = get_logger(__name__)


class NetworkOptimizerAgent:
    """
    Агент, который рассчитывает последствия закрытия/перемещения ВСП
    """

    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self.tools = [calculate_vsp_closure, calculate_vsp_relocation, get_vsp_info]
        self.tools_description = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])

        self.prompt = NETWORK_OPTIMIZER_PROMPT.format(tools_description=self.tools_description)
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

            logger.info(f"ThreadID: {state.thread_id}: Starting NetworkOptimizer agent")

            context_parts = []
            if state.query_params:
                params = state.query_params
                logger.info(f"ThreadID: {state.thread_id}: Получены параметры запроса: "
                            f"is_close={params.is_close}, "
                            f"is_cs={params.is_cs}, "
                            f"is_bt={params.is_bt}, "
                            f"координат={len(params.coordinates)}")

                context_parts.append("## ПАРАМЕТРЫ ЗАПРОСА:")
                if params.is_close:
                    context_parts.append(f"ВСП для закрытия (is_close): {params.is_close}")
                if params.is_cs:
                    context_parts.append(f"ВСП для возврата в сеть (is_cs): {params.is_cs}")
                if params.is_bt:
                    context_parts.append(f"ВСП для приема клиентопотока (is_bt): {params.is_bt}")
                if params.coordinates:
                    context_parts.append(f"Координаты ВСП: {params.coordinates}")
            else:
                logger.warning(f"ThreadID: {state.thread_id}: Параметры запроса не найдены в state")

            if state.messages:
                messages = state.messages.copy()
                if context_parts:
                    context_message = HumanMessage(content="\n".join(context_parts))
                    messages.append(context_message)
            else:
                user_content = state.user_query
                if context_parts:
                    user_content = "\n\n".join([state.user_query] + context_parts)
                messages = [HumanMessage(content=user_content)]

            resp = self.agent.invoke({"messages": messages})

            raw = resp["messages"][-1].content if resp["messages"] else ""
            out = raw if isinstance(raw, str) else str(raw)
            logger.info(
                "ThreadID: %s: NetworkOptimizer завершён, result_len=%s",
                state.thread_id,
                len(out),
            )
            return {
                "messages": resp["messages"],
                "result": out,
            }

        except ParentCommand:
            logger.info(f"ThreadID: {state.thread_id}: NetworkOptimizer agent completed, transitioning to next agent")
            raise
        except Exception as e:
            logger.error(f"ThreadID: {state.thread_id}: NetworkOptimizer agent error: {str(e)}")
            return {
                "error": str(e),
                "agent_type": "network_optimizer_agent",
                "error_type": type(e).__name__
            }

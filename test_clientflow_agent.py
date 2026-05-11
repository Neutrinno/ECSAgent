"""Простой smoke-тест конкретной ноды client_flow_agent."""

from src.core.agents.clientflow_agent.client_flow_agent import ClientFlowAgent
from src.core.graph_state import GraphState, PlanStep
from src.core.llm_utils.llm_factory import llm


def main() -> None:
    step_id = "step_1"
    urf_code = "059_6734_122"

    state = GraphState(
        user_query=f"Проверь динамику клиентопотока ВСП {urf_code}",
        urf_codes=[urf_code],
        plan_steps=[
            PlanStep(
                step_id=step_id,
                agent="client_flow_agent",
                task=f"Проанализировать динамику клиентопотока ВСП {urf_code} за последние 6 месяцев",
                depends_on=[],
            )
        ],
        current_step_id=step_id,
    )

    agent = ClientFlowAgent(llm=llm)
    patch = agent.process_state(state)

    print("=== PATCH FROM client_flow_agent ===")
    print(patch)


if __name__ == "__main__":
    main()

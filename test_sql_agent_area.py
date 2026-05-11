"""Простой smoke-тест конкретной ноды sql_agent."""

from src.core.agents.sql_agent.sql_agent import SQLAgent
from src.core.graph_state import GraphState, PlanStep
from src.core.llm_utils.llm_factory import llm


def main() -> None:
    step_id = "step_1"
    urf_code = "059_6734_122"

    state = GraphState(
        user_query=f"Какая площадь у ВСП 059_6734_122?",
        urf_codes=[urf_code],
        plan_steps=[
            PlanStep(
                step_id=step_id,
                agent="sql_agent",
                task=f"Получить фактическую и нормативную площадь ВСП {urf_code}",
                depends_on=[],
            )
        ],
        current_step_id=step_id,
    )

    agent = SQLAgent(llm=llm)
    patch = agent.process_state(state)

    print("=== PATCH FROM sql_agent ===")
    print(patch)


if __name__ == "__main__":
    main()

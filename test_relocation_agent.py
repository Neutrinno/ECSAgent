"""Простой smoke-тест конкретной ноды relocation_agent."""

from src.core.agents.relocation_agent.relocation_agent import RelocationAgent
from src.core.graph_state import GraphState, PlanStep
from src.core.llm_utils.llm_factory import llm


def main() -> None:
    step_id = "step_1"
    urf_code = "059_6734_122"

    state = GraphState(
        user_query=f"Рассчитать перемещение ВСП {urf_code}",
        urf_codes=[urf_code],
        plan_steps=[
            PlanStep(
                step_id=step_id,
                agent="relocation_agent",
                task=(
                    f"Рассчитать перемещение ВСП {urf_code} на новые координаты "
                    "55.7558, 37.6176 и оценить эффект по метрикам"
                ),
                depends_on=[],
            )
        ],
        current_step_id=step_id,
    )

    agent = RelocationAgent(llm=llm)
    patch = agent.process_state(state)

    print("=== PATCH FROM relocation_agent ===")
    print(patch)


if __name__ == "__main__":
    main()

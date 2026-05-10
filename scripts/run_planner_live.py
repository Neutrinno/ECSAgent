import argparse
import json
from uuid import uuid4

from src.core.agents.planner_agent.planner_agent import PlannerAgent
from src.core.graph_state import GraphState


def main() -> int:
    parser = argparse.ArgumentParser(description="Live вызов planner_agent без pytest")
    parser.add_argument(
        "--query",
        type=str,
        required=True,
        help="Запрос пользователя",
    )
    args = parser.parse_args()

    try:
        from src.core.llm_utils.llm_factory import llm
    except Exception as e:
        print(f"Ошибка инициализации llm_factory: {e}")
        return 1

    if llm is None:
        print("LLM не инициализирован")
        return 1

    planner = PlannerAgent(llm=llm)
    state = GraphState(
        user_query=args.query,
        thread_id=uuid4(),
    )
    result = planner.process_state(state)

    payload = {
        "next_agent": result.next_agent,
        "plan_summary": result.plan_summary,
        "plan_steps": result.plan_steps,
        "plan_risks": result.plan_risks,
        "error": result.error,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

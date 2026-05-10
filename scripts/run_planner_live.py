import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.agents.planner_agent.planner_agent import PlannerAgent
from src.core.graph_state import GraphState


def _patch_to_jsonable(patch: dict) -> dict:
    """Pydantic-модели в патче → dict для json.dumps."""
    out = dict(patch)
    steps = out.get("plan_steps")
    if steps:
        out["plan_steps"] = [
            s.model_dump() if hasattr(s, "model_dump") else s for s in steps
        ]
        out["first_step_agent"] = out["plan_steps"][0].get("agent")
    sr = out.get("step_results")
    if isinstance(sr, dict):
        out["step_results"] = {
            k: v.model_dump() if hasattr(v, "model_dump") else v for k, v in sr.items()
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Live вызов planner_agent без pytest")
    parser.add_argument("--query", type=str, required=True, help="Запрос пользователя")
    args = parser.parse_args()

    try:
        from src.core.llm_utils.llm_factory import llm
    except Exception as e:
        print(f"Ошибка инициализации llm_factory: {e}", file=sys.stderr)
        return 1

    if llm is None:
        print("LLM не инициализирован", file=sys.stderr)
        return 1

    planner = PlannerAgent(llm=llm)
    state = GraphState(user_query=args.query, thread_id=uuid4())
    patch = planner.process_state(state)

    if not isinstance(patch, dict):
        print(json.dumps({"error": "ожидался dict от process_state"}, ensure_ascii=False))
        return 1

    payload = _patch_to_jsonable(patch)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

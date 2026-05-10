import argparse
import json
from uuid import uuid4

from src.core.agents.control_layer.control_layer import ControlLayer
from src.core.graph_state import GraphState


def main() -> int:
    parser = argparse.ArgumentParser(description="Live вызов control_layer без pytest")
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

    control_layer = ControlLayer(llm=llm)
    state = GraphState(
        user_query=args.query,
        thread_id=uuid4(),
    )
    result = control_layer.process_state(state)

    payload = {
        "current_agent": result.get("current_agent"),
        "status": result.get("status"),
        "need_replan": result.get("need_replan"),
        "need_retry": result.get("need_retry"),
        "urf_codes": result.get("urf_codes"),
        "control_layer_answer": result.get("control_layer_answer"),
        "final_result": result.get("final_result"),
        "error": result.get("error"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

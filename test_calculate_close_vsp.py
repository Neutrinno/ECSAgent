"""Простой smoke-тест calculate_close_vsp: вызов через invoke и печать ответа агенту."""

from src.core.agents.network_optimizer_agent.network_optimizer_tools import calculate_close_vsp


def main() -> None:
    result = calculate_close_vsp.invoke({"closing_urf_list": ["059_6734_122"]})
    print(result)


if __name__ == "__main__":
    main()

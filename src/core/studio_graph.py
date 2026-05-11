from pathlib import Path

from dotenv import load_dotenv

from src.core.agents.service_manager import service_manager


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# Экспорт для LangGraph Studio/CLI.
graph = service_manager.agent_graph

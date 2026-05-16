from pathlib import Path

from dotenv import load_dotenv

from src.core.agents.service_manager import service_manager


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# Экспорт для LangGraph Studio/CLI (без MemorySaver — иначе падает загрузка API).
graph = service_manager.studio_graph

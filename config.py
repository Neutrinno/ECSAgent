# config.py
from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv()

cert_folder = Path(__file__).parent / "cert"

GIGA_CERT_FILE = str(cert_folder / "cert_pem.txt")
GIGA_KEY_FILE = str(cert_folder / "private_key.txt")

GIGACHAT_URL = os.environ.get("GIGACHAT_URL")
GIGA_BASE_URL = f"{GIGACHAT_URL}/v1"

print(f"\nBase URL: {GIGA_BASE_URL}")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "qwen/qwen3.6-flash")

REPORTS_DIRECTORY = "data"

LANGSMITH_TRACING = os.environ.get("LANGSMITH_TRACING", "false").lower() in ("true", "1", "yes")
LANGSMITH_ENDPOINT = os.environ.get("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
LANGSMITH_API_KEY = os.environ.get("LANGSMITH_API_KEY")
LANGSMITH_PROJECT = os.environ.get("LANGSMITH_PROJECT", "default")

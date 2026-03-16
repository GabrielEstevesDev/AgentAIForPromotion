from pathlib import Path
from dotenv import load_dotenv
import os

_backend_env = Path(__file__).parent / ".env"
_root_env = Path(__file__).parent.parent / ".env"
load_dotenv(_backend_env, override=True)
load_dotenv(_root_env, override=True)

ROOT_DIR = Path(__file__).parent.parent
DOCS_DIR = ROOT_DIR / "docs"
DB_PATH = ROOT_DIR / "dev.db"
CHROMA_DIR = Path(__file__).parent / "chroma_db"
CHARTS_DIR = Path(__file__).parent / "charts"
CHARTS_DIR.mkdir(exist_ok=True)
BACKEND_BASE_URL = "http://127.0.0.1:8001"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_MODEL = "gpt-4o-mini-2024-07-18"
EMBEDDING_MODEL = "text-embedding-3-small"

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

CHROMA_COLLECTION = "ecommerce_docs"
RAG_CHUNK_SIZE = 800
RAG_CHUNK_OVERLAP = 100
RAG_TOP_K = 5

EXECUTOR_TIMEOUT_SEC = 30

# Set to True to fall back to the legacy create_react_agent implementation
USE_LEGACY_AGENT = False


def require_keys(*keys: str) -> None:
    missing = [key for key in keys if not os.environ.get(key)]
    if missing:
        raise EnvironmentError(
            f"Missing environment variables: {', '.join(missing)}. "
            "Check backend/.env or the project root .env."
        )

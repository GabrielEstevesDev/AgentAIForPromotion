from pathlib import Path
from dotenv import load_dotenv
import os

_backend_env = Path(__file__).parent / ".env"
_root_env = Path(__file__).parent.parent / ".env"
load_dotenv(_backend_env, override=True)
load_dotenv(_root_env, override=True)

ROOT_DIR = Path(__file__).parent.parent
DOCS_DIR = Path(os.environ.get("DOCS_DIR", str(ROOT_DIR / "docs")))
DB_PATH = Path(os.environ.get("DB_PATH", str(ROOT_DIR / "dev.db")))
CHROMA_DIR = Path(os.environ.get("CHROMA_DIR", str(Path(__file__).parent / "chroma_db")))
CHARTS_DIR = Path(os.environ.get("CHARTS_DIR", str(Path(__file__).parent / "charts")))
CHARTS_DIR.mkdir(exist_ok=True)
BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://127.0.0.1:8001")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_MODEL = "gpt-4o-mini-2024-07-18"
EMBEDDING_MODEL = "text-embedding-3-small"

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

CHROMA_COLLECTION = "ecommerce_docs"
RAG_CHUNK_SIZE = 800
RAG_CHUNK_OVERLAP = 100
RAG_TOP_K = 5

EXECUTOR_TIMEOUT_SEC = 30

# Legacy agent toggle
USE_LEGACY_AGENT = os.environ.get("USE_LEGACY_AGENT", "false").lower() == "true"

# Rate limiting
ADMIN_SECRET_TOKEN = os.environ.get("ADMIN_SECRET_TOKEN", "")
RATE_LIMIT_GLOBAL = int(os.environ.get("RATE_LIMIT_GLOBAL", "100"))
RATE_LIMIT_USER = int(os.environ.get("RATE_LIMIT_USER", "10"))


def require_keys(*keys: str) -> None:
    missing = [key for key in keys if not os.environ.get(key)]
    if missing:
        raise EnvironmentError(
            f"Missing environment variables: {', '.join(missing)}. "
            "Check backend/.env or the project root .env."
        )

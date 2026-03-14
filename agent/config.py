from pathlib import Path
from dotenv import load_dotenv
import os

# Charge les deux .env pour couvrir tous les cas (agent/.env et racine/.env)
_agent_env = Path(__file__).parent / ".env"
_root_env  = Path(__file__).parent.parent / ".env"
load_dotenv(_agent_env, override=True)
load_dotenv(_root_env, override=False)  # racine en fallback, sans écraser

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT_DIR   = Path(__file__).parent.parent
DOCS_DIR   = ROOT_DIR / "docs"
DB_PATH    = ROOT_DIR / "dev.db"
CHROMA_DIR = Path(__file__).parent / "chroma_db"

# ── OpenAI ─────────────────────────────────────────────────────────────────────
OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")
LLM_MODEL       = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"

# ── Tavily ─────────────────────────────────────────────────────────────────────
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

# ── RAG ────────────────────────────────────────────────────────────────────────
CHROMA_COLLECTION = "ecommerce_docs"
RAG_CHUNK_SIZE    = 800
RAG_CHUNK_OVERLAP = 100
RAG_TOP_K         = 5

# ── Python executor ────────────────────────────────────────────────────────────
EXECUTOR_TIMEOUT_SEC = 30

# ── Validation (crash tôt avec un message clair) ───────────────────────────────
def require_keys(*keys: str) -> None:
    """Appelle cette fonction au démarrage de l'agent pour valider les clés."""
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(
            f"Clés manquantes dans .env : {', '.join(missing)}\n"
            f"Vérifie agent/.env ou le .env à la racine du projet."
        )

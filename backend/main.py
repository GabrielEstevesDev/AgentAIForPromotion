import asyncio
import logging
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .agent import build_agent
from .db import get_connection
from .graph.stream import cleanup_thread_locks
from .routers import chat, charts, conversations, database_explorer, documents, purchase_orders

# Phase 2.2: Structured logging via structlog
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

# Also configure stdlib logging to go through structlog
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

logger = logging.getLogger(__name__)

# ── Periodic cleanup helpers ──

_CLEANUP_INTERVAL_SEC = 3600  # 1 hour
_CONVERSATION_MAX_AGE_HOURS = 24
_RATE_LIMIT_MAX_AGE_DAYS = 7


def _delete_old_conversations() -> list[str]:
    """Delete conversations older than _CONVERSATION_MAX_AGE_HOURS.

    Returns list of deleted conversation IDs for downstream cleanup.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=_CONVERSATION_MAX_AGE_HOURS)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id FROM Conversation WHERE updatedAt < ?", (cutoff,)
            ).fetchall()
            ids = [r["id"] for r in rows]
            if not ids:
                return []

            placeholders = ",".join("?" for _ in ids)
            conn.execute(f"DELETE FROM MessageTrace WHERE conversationId IN ({placeholders})", ids)
            conn.execute(f"DELETE FROM Message WHERE conversationId IN ({placeholders})", ids)
            conn.execute(f"DELETE FROM Conversation WHERE id IN ({placeholders})", ids)
            conn.commit()
            return ids
    except sqlite3.OperationalError as exc:
        logger.warning("Cleanup: failed to delete old conversations: %s", exc)
        return []


def _delete_old_rate_limits() -> int:
    """Delete RateLimit entries older than _RATE_LIMIT_MAX_AGE_DAYS."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_RATE_LIMIT_MAX_AGE_DAYS)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    try:
        with get_connection() as conn:
            cursor = conn.execute("DELETE FROM RateLimit WHERE date < ?", (cutoff,))
            conn.commit()
            return cursor.rowcount
    except sqlite3.OperationalError as exc:
        logger.warning("Cleanup: failed to delete old rate limits: %s", exc)
        return 0


def _cleanup_memory_saver(compiled_graph, thread_ids: list[str]) -> int:
    """Remove stale checkpoints from MemorySaver's in-memory storage."""
    checkpointer = getattr(compiled_graph, "checkpointer", None)
    if checkpointer is None:
        return 0
    storage = getattr(checkpointer, "storage", None)
    if not isinstance(storage, dict):
        return 0

    removed = 0
    for tid in thread_ids:
        # MemorySaver keys are tuples starting with the thread_id
        keys_to_remove = [k for k in storage if isinstance(k, tuple) and len(k) > 0 and k[0] == tid]
        for k in keys_to_remove:
            del storage[k]
            removed += 1
    return removed


def _run_cleanup(compiled_graph) -> None:
    """Run all cleanup tasks synchronously."""
    deleted_ids = _delete_old_conversations()
    rate_limits_deleted = _delete_old_rate_limits()

    mem_removed = 0
    locks_removed = 0
    if deleted_ids:
        mem_removed = _cleanup_memory_saver(compiled_graph, deleted_ids)
        locks_removed = cleanup_thread_locks(deleted_ids)

    logger.info(
        "Cleanup: conversations=%d, rate_limits=%d, checkpoints=%d, locks=%d",
        len(deleted_ids),
        rate_limits_deleted,
        mem_removed,
        locks_removed,
    )


async def _periodic_cleanup(compiled_graph) -> None:
    """Background loop that runs cleanup every _CLEANUP_INTERVAL_SEC."""
    while True:
        try:
            await asyncio.sleep(_CLEANUP_INTERVAL_SEC)
            _run_cleanup(compiled_graph)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Periodic cleanup error: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent = build_agent()

    # Phase 1.2: Cold-start warmup — preload ChromaDB vectorstore
    from .rag.retriever import _get_vectorstore
    try:
        _get_vectorstore()
        logger.info("ChromaDB vectorstore pre-loaded")
    except Exception as e:
        logger.warning("ChromaDB warmup failed: %s", e)

    # Phase 1.2: Warmup LLM connection pool (first HTTP/2 handshake is slow)
    from .graph.nodes import _llm_no_tools
    try:
        await _llm_no_tools.ainvoke([{"role": "user", "content": "ping"}])
        logger.info("LLM connection warmed up")
    except Exception:
        logger.info("LLM connection warmed up (ping failed but connection established)")

    # Startup cleanup + schedule periodic task
    _run_cleanup(app.state.agent)
    logger.info("Startup cleanup complete")
    cleanup_task = asyncio.create_task(_periodic_cleanup(app.state.agent))

    yield

    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="AgenticStack Backend", lifespan=lifespan)


# Phase 2.2: Request ID middleware for structured logging
class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(charts.router)
app.include_router(purchase_orders.router)
app.include_router(database_explorer.router)
app.include_router(documents.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


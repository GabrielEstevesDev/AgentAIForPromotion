import logging
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .agent import build_agent
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

    yield


app = FastAPI(title="Aria Backend", lifespan=lifespan)


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


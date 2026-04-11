import asyncio
import json
import logging
import re
import sqlite3
import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..agent import stream_agent
from ..config import ADMIN_SECRET_TOKEN, LLM_MODEL, RATE_LIMIT_GLOBAL, RATE_LIMIT_USER
from ..db import get_connection
from ..validators import check_summary_breakdown_coherence, validate_hitl_structure

# Regex to strip tool-status emoji lines before persisting content
# Strips tool/status emoji lines before persisting content
# Covers: ✨ Analyzing..., 🔍 Querying..., 📊 Looking up..., 📚 Searching..., 🌐 Searching..., 🐍 Running..., 📦 Processing...
_STATUS_LINE_RE = re.compile(r"\n*[\u2728\U0001f9e0\U0001f50d\U0001f4ca\U0001f4da\U0001f310\U0001f40d\U0001f4e6][^\n]*\.\.\.\n*")

# Matches chart image markdown links
_CHART_URL_RE = re.compile(r"!\[chart\]\([^\)]+\)")
# Matches hallucinated chart URLs (not served by /api/charts/)
_HALLUCINATED_CHART_RE = re.compile(r"!\[chart\]\((?!/api/charts/)[^\)]+\)")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    conversationId: str


def _handle_missing_table(exc: sqlite3.OperationalError) -> None:
    if "no such table" in str(exc).lower():
        raise HTTPException(
            status_code=500,
            detail="Conversation tables are missing. Run the Prisma migration for chat history first.",
        ) from exc
    raise exc


def _ensure_trace_table() -> None:
    """Create the MessageTrace table if it doesn't exist."""
    try:
        with get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS MessageTrace (
                    id TEXT PRIMARY KEY,
                    messageId TEXT NOT NULL,
                    conversationId TEXT NOT NULL,
                    traceData TEXT NOT NULL,
                    createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (messageId) REFERENCES Message(id),
                    FOREIGN KEY (conversationId) REFERENCES Conversation(id)
                )
            """)
            conn.commit()
    except Exception:
        pass  # Best effort


# Ensure tables exist on module load
_ensure_trace_table()


def _ensure_rate_limit_table() -> None:
    """Create the RateLimit table if it doesn't exist."""
    try:
        with get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS RateLimit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    userIdentifier TEXT NOT NULL,
                    createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
    except Exception:
        pass


_ensure_rate_limit_table()


def _get_real_ip(request: Request) -> str:
    """Extract the real client IP from the X-Real-IP header set by Caddy.

    Caddy strips any client-sent X-Real-IP and injects the true remote address,
    so this header is not spoofable. X-Forwarded-For is intentionally ignored
    because clients can pre-set it and trick naive parsers.
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    # Fallback for local dev (no Caddy in front)
    return request.client.host if request.client else "unknown"


def _check_rate_limit(request: Request) -> None:
    """Check global and per-user rate limits. Raises HTTPException(429) if exceeded."""
    # Admin bypass
    admin_token = request.headers.get("x-admin-token", "")
    if ADMIN_SECRET_TOKEN and admin_token == ADMIN_SECRET_TOKEN:
        return

    user_ip = _get_real_ip(request)

    with get_connection() as conn:
        global_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM RateLimit WHERE date(createdAt) = date('now')"
        ).fetchone()
        if global_count and global_count["cnt"] >= RATE_LIMIT_GLOBAL:
            raise HTTPException(
                status_code=429,
                detail=json.dumps({
                    "error": "global_limit",
                    "message": f"The platform has reached its daily capacity of {RATE_LIMIT_GLOBAL} messages. To keep this demo running smoothly, please try again tomorrow.",
                }),
            )

        user_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM RateLimit WHERE userIdentifier = ? AND date(createdAt) = date('now')",
            (user_ip,),
        ).fetchone()
        if user_count and user_count["cnt"] >= RATE_LIMIT_USER:
            raise HTTPException(
                status_code=429,
                detail=json.dumps({
                    "error": "user_limit",
                    "message": f"You've reached your daily limit of {RATE_LIMIT_USER} messages for this demo. Please come back tomorrow to try again!",
                }),
            )


def _record_rate_limit(request: Request) -> None:
    """Insert a rate-limit row for the current request."""
    user_ip = _get_real_ip(request)
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO RateLimit (userIdentifier) VALUES (?)",
                (user_ip,),
            )
            conn.commit()
    except Exception:
        pass


def _persist_messages(
    conversation_id: str,
    user_content: str,
    assistant_content: str,
    trace_data: list[dict] | None = None,
) -> None:
    try:
        with get_connection() as conn:
            conversation = conn.execute(
                "SELECT id FROM Conversation WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found.")

            conn.execute(
                """
                INSERT INTO Message (id, conversationId, role, content, createdAt)
                VALUES (?, ?, 'user', ?, CURRENT_TIMESTAMP)
                """,
                (str(uuid.uuid4()), conversation_id, user_content),
            )
            assistant_msg_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO Message (id, conversationId, role, content, createdAt)
                VALUES (?, ?, 'assistant', ?, CURRENT_TIMESTAMP)
                """,
                (assistant_msg_id, conversation_id, assistant_content),
            )

            # Persist trace data if available
            if trace_data:
                conn.execute(
                    """
                    INSERT INTO MessageTrace (id, messageId, conversationId, traceData, createdAt)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (str(uuid.uuid4()), assistant_msg_id, conversation_id, json.dumps(trace_data)),
                )

            conn.execute(
                """
                UPDATE Conversation
                SET updatedAt = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (conversation_id,),
            )
            conn.commit()
    except sqlite3.OperationalError as exc:
        _handle_missing_table(exc)


async def _auto_title_if_first(conversation_id: str, user_content: str) -> None:
    """Generate a short conversation title after the first message exchange."""
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM Message WHERE conversationId = ?",
                (conversation_id,),
            ).fetchone()
            if not row or row["cnt"] != 2:
                return

        llm = ChatOpenAI(model=LLM_MODEL, temperature=0)
        prompt = (
            "Generate a short, descriptive title (4-7 words max) for a conversation "
            f"that starts with this user question: {user_content[:300]}\n"
            "Respond with ONLY the title — no quotes, no trailing punctuation."
        )
        response = await llm.ainvoke(prompt)
        title = str(response.content).strip()[:80]
        if title:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE Conversation SET title = ?, updatedAt = CURRENT_TIMESTAMP WHERE id = ?",
                    (title, conversation_id),
                )
                conn.commit()
    except Exception:
        pass  # Title generation is best-effort


def _public_error_detail(exc: Exception) -> str:
    message = str(exc)
    lower_message = message.lower()

    if "invalid_api_key" in lower_message or "incorrect api key provided" in lower_message:
        return "The OpenAI API key is invalid or expired. Update OPENAI_API_KEY in the environment."

    if "authentication" in lower_message and "openai" in lower_message:
        return "OpenAI authentication failed. Check OPENAI_API_KEY in the environment."

    if "recursion" in lower_message or "recursionlimit" in lower_message:
        return "The question required too many steps. Try breaking it into smaller, more specific questions."

    if "timeout" in lower_message or "timed out" in lower_message:
        return "The request timed out. Try a simpler question or break it into smaller steps."

    return message


@router.post("")
async def chat(payload: ChatRequest, request: Request) -> EventSourceResponse:
    request_start = time.perf_counter()

    if not payload.messages:
        raise HTTPException(status_code=400, detail="At least one message is required.")

    last_message = payload.messages[-1]
    if last_message.role != "user":
        raise HTTPException(status_code=400, detail="The last message must be from the user.")

    # Rate-limit check (before any LLM work)
    _check_rate_limit(request)

    agent = request.app.state.agent
    user_content = last_message.content.strip()
    if not user_content:
        raise HTTPException(status_code=400, detail="User message cannot be empty.")

    # Record usage after validation passes
    _record_rate_limit(request)

    setup_dur = time.perf_counter() - request_start
    logger.info("PERF_LOG: [FastAPI Request Setup] - %.4fs", setup_dur)

    # Prefix used by stream.py to mark perf data in the token queue
    PERF_PREFIX = "\x00PERF:"
    # Prefix used by stream.py to mark trace data
    TRACE_PREFIX = "\x00TRACE:"

    async def event_generator():
        chunks: list[str] = []
        trace_data: list[dict] = []
        first_token_emitted = False
        try:
            async for token in stream_agent(agent, user_content, payload.conversationId):
                # Perf markers: emit as 'perf' SSE events, not 'token'
                if isinstance(token, str) and token.startswith(PERF_PREFIX):
                    yield {
                        "event": "perf",
                        "data": token[len(PERF_PREFIX):],  # already JSON
                    }
                    continue

                # Trace data: capture and forward as 'trace' SSE event
                if isinstance(token, str) and token.startswith(TRACE_PREFIX):
                    try:
                        trace_data = json.loads(token[len(TRACE_PREFIX):])
                    except json.JSONDecodeError:
                        pass
                    yield {
                        "event": "trace",
                        "data": token[len(TRACE_PREFIX):],
                    }
                    continue

                chunks.append(token)
                if not first_token_emitted and token:
                    first_token_emitted = True
                    ttft = time.perf_counter() - request_start
                    logger.info("PERF_LOG: [FastAPI TTFT (Request -> First SSE Token)] - %.3fs", ttft)
                    yield {
                        "event": "perf",
                        "data": json.dumps({"name": "FastAPI TTFT", "duration": round(ttft, 4)}),
                    }
                yield {
                    "event": "token",
                    "data": json.dumps({"token": token}),
                }

            assistant_content = "".join(chunks).strip()

            # Strip tool-status emoji lines before validation and persistence
            clean_content = _STATUS_LINE_RE.sub("", assistant_content).strip()

            # Strip hallucinated chart URLs (not from /api/charts/)
            clean_content = _HALLUCINATED_CHART_RE.sub("", clean_content)

            # Deduplicate chart URLs — keep only first occurrence of each
            _seen_charts: set[str] = set()
            def _dedup_chart(m: re.Match) -> str:
                url = m.group()
                if url in _seen_charts:
                    return ""
                _seen_charts.add(url)
                return url
            clean_content = _CHART_URL_RE.sub(_dedup_chart, clean_content)

            # Clean up any leftover blank lines from removed duplicates
            clean_content = re.sub(r"\n{3,}", "\n\n", clean_content).strip()

            # ── Post-processing validation ──
            coherence_note = check_summary_breakdown_coherence(clean_content)
            if coherence_note:
                clean_content += coherence_note
                yield {
                    "event": "token",
                    "data": json.dumps({"token": coherence_note}),
                }

            hitl_warnings = validate_hitl_structure(clean_content)
            if hitl_warnings:
                warning_text = "\n\n> " + " | ".join(hitl_warnings)
                logger.warning(
                    "HITL validation warnings for %s: %s",
                    payload.conversationId, hitl_warnings,
                )

            _persist_messages(payload.conversationId, user_content, clean_content, trace_data or None)
            asyncio.create_task(
                _auto_title_if_first(payload.conversationId, user_content)
            )
            total_request = time.perf_counter() - request_start
            logger.info("PERF_LOG: [Total Request Duration] - %.3fs", total_request)
            yield {
                "event": "perf",
                "data": json.dumps({"name": "Total Request Duration", "duration": round(total_request, 4)}),
            }
            yield {
                "event": "done",
                "data": json.dumps({"ok": True}),
            }
        except HTTPException as exc:
            yield {
                "event": "error",
                "data": json.dumps({"detail": exc.detail}),
            }
        except Exception as exc:
            logger.exception("Chat stream error for conversation %s", payload.conversationId)
            yield {
                "event": "error",
                "data": json.dumps({"detail": _public_error_detail(exc)}),
            }

    return EventSourceResponse(event_generator())

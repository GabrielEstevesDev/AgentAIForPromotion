import asyncio
import json
import logging
import sqlite3
import uuid

from fastapi import APIRouter, HTTPException, Request
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..agent import stream_agent
from ..config import LLM_MODEL
from ..db import get_connection

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


def _persist_messages(conversation_id: str, user_content: str, assistant_content: str) -> None:
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
            conn.execute(
                """
                INSERT INTO Message (id, conversationId, role, content, createdAt)
                VALUES (?, ?, 'assistant', ?, CURRENT_TIMESTAMP)
                """,
                (str(uuid.uuid4()), conversation_id, assistant_content),
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
    if not payload.messages:
        raise HTTPException(status_code=400, detail="At least one message is required.")

    last_message = payload.messages[-1]
    if last_message.role != "user":
        raise HTTPException(status_code=400, detail="The last message must be from the user.")

    agent = request.app.state.agent
    user_content = last_message.content.strip()
    if not user_content:
        raise HTTPException(status_code=400, detail="User message cannot be empty.")

    async def event_generator():
        chunks: list[str] = []
        try:
            async for token in stream_agent(agent, user_content, payload.conversationId):
                chunks.append(token)
                yield {
                    "event": "token",
                    "data": json.dumps({"token": token}),
                }

            assistant_content = "".join(chunks).strip()
            _persist_messages(payload.conversationId, user_content, assistant_content)
            asyncio.create_task(
                _auto_title_if_first(payload.conversationId, user_content)
            )
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

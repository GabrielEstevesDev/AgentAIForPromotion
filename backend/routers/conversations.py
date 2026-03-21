import json
import sqlite3
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..db import get_connection

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _ensure_session_column() -> None:
    """Add sessionId column to Conversation table if it doesn't exist."""
    try:
        with get_connection() as conn:
            conn.execute(
                "ALTER TABLE Conversation ADD COLUMN sessionId TEXT DEFAULT NULL"
            )
            conn.commit()
    except sqlite3.OperationalError:
        # Column already exists — ignore
        pass


_ensure_session_column()


class ConversationCreate(BaseModel):
    title: str = "New conversation"
    sessionId: str | None = None


class ConversationUpdate(BaseModel):
    title: str


def _handle_missing_table(exc: sqlite3.OperationalError) -> None:
    if "no such table" in str(exc).lower():
        raise HTTPException(
            status_code=500,
            detail="Conversation tables are missing. Run the Prisma migration for chat history first.",
        ) from exc
    raise exc


@router.get("")
def list_conversations(sessionId: str | None = Query(default=None)) -> list[dict]:
    try:
        with get_connection() as conn:
            if sessionId:
                rows = conn.execute(
                    """
                    SELECT id, title, createdAt, updatedAt
                    FROM Conversation
                    WHERE sessionId = ?
                    ORDER BY updatedAt DESC
                    """,
                    (sessionId,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, title, createdAt, updatedAt
                    FROM Conversation
                    ORDER BY updatedAt DESC
                    """
                ).fetchall()
            return rows
    except sqlite3.OperationalError as exc:
        _handle_missing_table(exc)


@router.post("")
def create_conversation(payload: ConversationCreate) -> dict:
    try:
        with get_connection() as conn:
            conversation_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO Conversation (id, title, sessionId, createdAt, updatedAt)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (conversation_id, payload.title, payload.sessionId),
            )
            row = conn.execute(
                """
                SELECT id, title, createdAt, updatedAt
                FROM Conversation
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
            conn.commit()
            return row
    except sqlite3.OperationalError as exc:
        _handle_missing_table(exc)


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str) -> dict:
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, title, createdAt, updatedAt
                FROM Conversation
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Conversation not found.")
            return row
    except sqlite3.OperationalError as exc:
        _handle_missing_table(exc)


@router.get("/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str) -> list[dict]:
    try:
        with get_connection() as conn:
            conversation = conn.execute(
                "SELECT id FROM Conversation WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found.")

            rows = conn.execute(
                """
                SELECT id, conversationId, role, content, createdAt
                FROM Message
                WHERE conversationId = ?
                ORDER BY datetime(createdAt) ASC, rowid ASC
                """,
                (conversation_id,),
            ).fetchall()
            return rows
    except sqlite3.OperationalError as exc:
        _handle_missing_table(exc)


@router.patch("/{conversation_id}")
def rename_conversation(conversation_id: str, payload: ConversationUpdate) -> dict:
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE Conversation
                SET title = ?, updatedAt = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (payload.title, conversation_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Conversation not found.")

            row = conn.execute(
                """
                SELECT id, title, createdAt, updatedAt
                FROM Conversation
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
            conn.commit()
            return row
    except sqlite3.OperationalError as exc:
        _handle_missing_table(exc)


@router.get("/{conversation_id}/traces")
def get_conversation_traces(conversation_id: str) -> list[dict]:
    """Get all trace data for a conversation, keyed by messageId."""
    try:
        with get_connection() as conn:
            conversation = conn.execute(
                "SELECT id FROM Conversation WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found.")

            # Check if table exists
            table_check = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='MessageTrace'"
            ).fetchone()
            if not table_check:
                return []

            rows = conn.execute(
                """
                SELECT messageId, traceData, createdAt
                FROM MessageTrace
                WHERE conversationId = ?
                ORDER BY datetime(createdAt) ASC
                """,
                (conversation_id,),
            ).fetchall()

            result = []
            for row in rows:
                try:
                    trace = json.loads(row["traceData"])
                except (json.JSONDecodeError, TypeError):
                    trace = []
                result.append({
                    "messageId": row["messageId"],
                    "trace": trace,
                    "createdAt": row["createdAt"],
                })
            return result
    except sqlite3.OperationalError as exc:
        _handle_missing_table(exc)


@router.get("/{conversation_id}/traces/{message_id}")
def get_message_trace(conversation_id: str, message_id: str) -> dict:
    """Get trace data for a specific message."""
    try:
        with get_connection() as conn:
            table_check = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='MessageTrace'"
            ).fetchone()
            if not table_check:
                raise HTTPException(status_code=404, detail="No trace data available.")

            row = conn.execute(
                """
                SELECT messageId, traceData, createdAt
                FROM MessageTrace
                WHERE conversationId = ? AND messageId = ?
                """,
                (conversation_id, message_id),
            ).fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="No trace found for this message.")

            try:
                trace = json.loads(row["traceData"])
            except (json.JSONDecodeError, TypeError):
                trace = []

            return {
                "messageId": row["messageId"],
                "trace": trace,
                "createdAt": row["createdAt"],
            }
    except sqlite3.OperationalError as exc:
        _handle_missing_table(exc)


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict:
    try:
        with get_connection() as conn:
            # Check existence first
            row = conn.execute(
                "SELECT id FROM Conversation WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Conversation not found.")

            # Delete in FK-safe order: traces → messages → conversation
            conn.execute(
                "DELETE FROM MessageTrace WHERE conversationId = ?",
                (conversation_id,),
            )
            conn.execute(
                "DELETE FROM Message WHERE conversationId = ?",
                (conversation_id,),
            )
            conn.execute(
                "DELETE FROM Conversation WHERE id = ?",
                (conversation_id,),
            )
            conn.commit()
            return {"ok": True}
    except sqlite3.OperationalError as exc:
        _handle_missing_table(exc)

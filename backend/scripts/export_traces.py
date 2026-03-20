"""
Export all conversations with their messages and trace inspector data to JSON.

Usage (from repo root):
    "agent/.venv/Scripts/python.exe" backend/scripts/export_traces.py

Output: backend/scripts/conversations_with_traces.json
"""

import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "dev.db"
OUTPUT_PATH = Path(__file__).resolve().parent / "conversations_with_traces.json"


def dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def export():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = dict_factory
    conn.execute("PRAGMA journal_mode=WAL")

    trace_table_exists = has_table(conn, "MessageTrace")

    # Fetch all conversations
    conversations = conn.execute(
        "SELECT id, title, createdAt, updatedAt FROM Conversation ORDER BY datetime(createdAt) ASC"
    ).fetchall()

    result = []

    for conv in conversations:
        cid = conv["id"]

        # Fetch messages for this conversation
        messages = conn.execute(
            """
            SELECT id, role, content, createdAt
            FROM Message
            WHERE conversationId = ?
            ORDER BY datetime(createdAt) ASC
            """,
            (cid,),
        ).fetchall()

        # Build a messageId -> trace mapping
        trace_map: dict[str, list] = {}
        if trace_table_exists:
            traces = conn.execute(
                """
                SELECT messageId, traceData
                FROM MessageTrace
                WHERE conversationId = ?
                """,
                (cid,),
            ).fetchall()
            for t in traces:
                try:
                    trace_map[t["messageId"]] = json.loads(t["traceData"])
                except (json.JSONDecodeError, TypeError):
                    trace_map[t["messageId"]] = []

        # Attach trace to each message
        enriched_messages = []
        for msg in messages:
            entry = {
                "id": msg["id"],
                "role": msg["role"],
                "content": msg["content"],
                "createdAt": msg["createdAt"],
            }
            trace = trace_map.get(msg["id"])
            if trace:
                entry["trace"] = trace
            enriched_messages.append(entry)

        result.append({
            "id": cid,
            "title": conv["title"],
            "createdAt": conv["createdAt"],
            "updatedAt": conv["updatedAt"],
            "messages": enriched_messages,
        })

    conn.close()

    OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    # Summary
    total_msgs = sum(len(c["messages"]) for c in result)
    total_traces = sum(
        1 for c in result for m in c["messages"] if "trace" in m
    )
    print(f"Exported {len(result)} conversations, {total_msgs} messages, {total_traces} traces")
    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    export()

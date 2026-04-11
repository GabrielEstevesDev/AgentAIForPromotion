import sqlite3

from fastapi import APIRouter, HTTPException, Query

from ..db import get_connection

router = APIRouter(prefix="/api/database", tags=["database"])

# Tables to hide from the public Database Explorer.
# Customer is hidden because it contains PII (name, email, phone).
_HIDDEN_TABLES = {
    "Customer",
    "MessageTrace",
    "ApiUsage",
    "RateLimit",
    "Conversation",
    "Message",
}


@router.get("/tables")
def list_tables() -> list[dict]:
    """Return all user tables with row counts."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_prisma_%' "
            "ORDER BY name"
        )
        tables = [row["name"] for row in cursor.fetchall() if row["name"] not in _HIDDEN_TABLES]

        result = []
        for table_name in tables:
            count_row = conn.execute(f'SELECT COUNT(*) AS cnt FROM "{table_name}"').fetchone()
            result.append({"name": table_name, "rowCount": count_row["cnt"]})

        return result


@router.get("/tables/{table_name}")
def get_table(
    table_name: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Return columns and paginated rows for a specific table."""
    with get_connection() as conn:
        # Validate table exists
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        ).fetchone()

        if not exists or table_name in _HIDDEN_TABLES:
            raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")

        # Get total count
        total_row = conn.execute(f'SELECT COUNT(*) AS cnt FROM "{table_name}"').fetchone()
        total = total_row["cnt"]

        # Get rows with pagination
        rows = conn.execute(
            f'SELECT * FROM "{table_name}" LIMIT ? OFFSET ?',
            (limit, offset),
        ).fetchall()

        # Extract column names from the first row, or from PRAGMA if empty
        if rows:
            columns = list(rows[0].keys())
        else:
            pragma_rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
            columns = [r["name"] for r in pragma_rows]

        return {"columns": columns, "rows": rows, "total": total}

import sqlite3

from langchain_core.tools import tool

from ..config import DB_PATH


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _to_markdown_table(columns: list[str], rows: list[sqlite3.Row]) -> str:
    """Format query results as a GitHub-flavored markdown table."""
    # Build header
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    data_rows = []
    for row in rows:
        cells = [str(value) if value is not None else "" for value in row]
        data_rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, separator] + data_rows)


@tool
def sql_query(query: str) -> str:
    """Execute a read-only SQL SELECT query against the e-commerce SQLite database.
    Returns the SQL query and results formatted as markdown (sql block + table).
    """
    query = query.strip()

    if not query.upper().startswith("SELECT"):
        return "Error: only SELECT queries are permitted."

    conn = None
    try:
        conn = _get_connection()
        cursor = conn.execute(query)
        rows = cursor.fetchmany(100)

        if not rows:
            return "Query returned no results."

        columns = [desc[0] for desc in cursor.description]
        table = _to_markdown_table(columns, rows)

        count_note = f"\n\n_{len(rows)} row(s) returned"
        if len(rows) == 100:
            count_note += " — limited to 100"
        count_note += "_"

        return f"{table}{count_note}"

    except sqlite3.Error as exc:
        return f"SQL Error: {exc}"
    finally:
        if conn is not None:
            conn.close()

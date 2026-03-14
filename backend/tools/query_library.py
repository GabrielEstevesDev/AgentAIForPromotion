import sqlite3

from langchain_core.tools import tool

from ..config import DB_PATH
from ..queries.library import QUERY_LIBRARY


def _run_query(sql: str) -> str:
    """Execute a pre-built SQL query and return a markdown table."""
    conn = None
    try:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.execute("PRAGMA query_only = ON")
        cursor = conn.execute(sql)
        rows = cursor.fetchmany(100)

        if not rows:
            return "Query returned no results."

        columns = [desc[0] for desc in cursor.description]
        header = "| " + " | ".join(columns) + " |"
        separator = "| " + " | ".join("---" for _ in columns) + " |"
        data_rows = [
            "| " + " | ".join(str(v) if v is not None else "" for v in row) + " |"
            for row in rows
        ]
        table = "\n".join([header, separator] + data_rows)

        note = f"\n\n_{len(rows)} row(s) returned"
        if len(rows) == 100:
            note += " — limited to 100"
        note += "_"

        return f"{table}{note}"

    except sqlite3.Error as exc:
        return f"SQL Error: {exc}"
    finally:
        if conn is not None:
            conn.close()


@tool
def query_library(query_name: str) -> str:
    """Execute a pre-built SQL query from the library by name.

    Use query_name='list' to get all available queries and their descriptions.
    Pre-built queries are faster and more reliable than writing SQL from scratch —
    prefer them whenever a query name matches the user's intent.

    Available categories: sales/revenue, products, inventory, orders, customers,
    reviews, api_usage.
    """
    if query_name.strip().lower() == "list":
        lines = ["**Available pre-built queries:**\n"]
        for name, meta in QUERY_LIBRARY.items():
            lines.append(f"- `{name}` — {meta['description']}")
        return "\n".join(lines)

    entry = QUERY_LIBRARY.get(query_name.strip())
    if entry is None:
        names = ", ".join(f"`{k}`" for k in QUERY_LIBRARY)
        return (
            f"Unknown query name: '{query_name}'.\n"
            f"Call with query_name='list' to see all options, or choose from: {names}"
        )

    return _run_query(entry["sql"])

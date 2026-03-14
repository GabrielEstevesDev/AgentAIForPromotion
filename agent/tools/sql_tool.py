import sqlite3
from langchain_core.tools import tool
from config import DB_PATH


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")  # enforce read-only at SQLite level
    return conn


@tool
def sql_query(query: str) -> str:
    """
    Execute a read-only SQL SELECT query against the e-commerce SQLite database.

    Schema (camelCase columns, Prisma-generated):
      Customer  : id, firstName, lastName, email, phone, createdAt
      Product   : id, name, description, price, category, sku
      "Order"   : id, customerId, orderDate, status, totalAmount
                  (status: 'Pending' | 'Shipped' | 'Delivered' | 'Cancelled')
      OrderItem : id, orderId, productId, quantity, unitPrice
      Inventory : id, productId, stockLevel, lastRestock
      Review    : id, productId, customerId, rating, comment, createdAt
      ApiUsage  : id, date, requestCount, totalTokens

    RULES:
    - Only SELECT statements are allowed.
    - "Order" MUST be quoted (reserved word): SELECT * FROM "Order"
    - Use camelCase for all column names.
    - Use JOINs to traverse relations.

    Returns a formatted table of results (max 100 rows).
    """
    query = query.strip()

    # Reject non-SELECT at application level (belt-and-suspenders)
    if not query.upper().startswith("SELECT"):
        return "Error: only SELECT queries are permitted."

    try:
        conn = _get_connection()
        cursor = conn.execute(query)
        rows = cursor.fetchmany(100)

        if not rows:
            return "Query returned no results."

        # Format as readable table
        columns = [desc[0] for desc in cursor.description]
        header = " | ".join(columns)
        separator = "-" * len(header)
        lines = [header, separator]
        for row in rows:
            lines.append(" | ".join(str(v) if v is not None else "NULL" for v in row))

        count_note = f"\n({len(rows)} row(s) returned)" + (
            " [limited to 100]" if len(rows) == 100 else ""
        )
        return "\n".join(lines) + count_note

    except sqlite3.Error as e:
        return f"SQL Error: {e}"
    finally:
        conn.close()

import sqlite3
import time

import aiosqlite
from langchain_core.tools import tool

from ..config import DB_PATH

# Phase 3.2: Simple TTL cache for query results (60s)
_SQL_CACHE: dict[str, tuple[float, str]] = {}
_SQL_CACHE_TTL = 60.0


def _to_markdown_table(columns: list[str], rows: list) -> str:
    """Format query results as a GitHub-flavored markdown table."""
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    data_rows = []
    for row in rows:
        cells = [str(value) if value is not None else "" for value in row]
        data_rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, separator] + data_rows)


@tool
async def sql_query(query: str) -> str:
    """Execute a read-only SQL SELECT query against the e-commerce SQLite database.
    Returns results as a markdown table. Use only when no query_library query fits.

    DATABASE SCHEMA (SQLite, camelCase columns):
      Customer      : id, firstName, lastName, email, phone, createdAt
      Product       : id, name, description, price, category, sku
      "Order"       : id, customerId, orderDate, status, totalAmount
                      status: 'Pending' | 'Shipped' | 'Delivered' | 'Cancelled'
      OrderItem     : id, orderId, productId, quantity, unitPrice
      Inventory     : id, productId, stockLevel, lastRestock
      Review        : id, productId, customerId, rating, comment, createdAt
      ApiUsage      : id, date, requestCount, totalTokens
      Supplier      : id, name, email, phone, createdAt
      PurchaseOrder : id, supplierId, createdAt, status, totalAmount
      PurchaseOrderItem : id, purchaseOrderId, productId (nullable), sku, name, quantity, unitCost

    SQL RULES:
    - "Order" is reserved — ALWAYS quote it: SELECT * FROM "Order"
    - All columns are camelCase: firstName, customerId, orderDate
    - Only SELECT statements allowed
    - Never SELECT `id` columns (UUIDs) unless the user asks
    - ALWAYS exclude Cancelled orders unless asked: WHERE status != 'Cancelled'
    - Use relative dates: date('now', '-30 days'). NEVER hardcode dates.
    - State the exact period in your response: "Last 30 days: Feb 12 – Mar 14, 2026"
    - TOP N / BOTTOM N: If the user asks for 'Top N' or 'Bottom N', ALWAYS use ORDER BY + LIMIT N.
      Example: SELECT p.name, i.stockLevel FROM Inventory i JOIN Product p ON i.productId = p.id ORDER BY i.stockLevel DESC LIMIT 15
    """
    query = query.strip()

    if not query.upper().startswith("SELECT"):
        return "Error: only SELECT queries are permitted."

    # Phase 3.2: Check cache
    cache_key = query.strip().lower()
    cached = _SQL_CACHE.get(cache_key)
    if cached and (time.time() - cached[0]) < _SQL_CACHE_TTL:
        return cached[1]

    # Phase 3.3: True async SQLite via aiosqlite
    try:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute("PRAGMA query_only = ON")
            cursor = await db.execute(query)
            columns = [desc[0] for desc in cursor.description]
            rows = await cursor.fetchmany(100)

            if not rows:
                return "Query returned no results."

            table = _to_markdown_table(columns, rows)

            count_note = f"\n\n_{len(rows)} row(s) returned"
            if len(rows) == 100:
                count_note += " — limited to 100"
            count_note += "_"

            result = f"{table}{count_note}"
            _SQL_CACHE[cache_key] = (time.time(), result)
            return result

    except Exception as exc:
        return f"SQL Error: {exc}"

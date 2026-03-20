import datetime
import json
import time

import aiosqlite
from langchain_core.tools import tool

from ..config import DB_PATH
from ..queries.library import QUERY_LIBRARY

# Phase 3.2: Simple TTL cache for query results (60s)
_QL_CACHE: dict[str, tuple[float, str]] = {}
_QL_CACHE_TTL = 60.0


async def _run_query(sql: str) -> str:
    """Execute a pre-built SQL query and return a markdown table (async)."""
    try:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute("PRAGMA query_only = ON")
            cursor = await db.execute(sql)
            columns = [desc[0] for desc in cursor.description]
            rows = await cursor.fetchmany(100)

            if not rows:
                return "Query returned no results."

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

    except Exception as exc:
        return f"SQL Error: {exc}"


def _sql_string(value: str) -> str:
    """Escape a Python string for safe interpolation into a library-owned SQL template."""
    return value.replace("'", "''")


async def _run_refund_order_context(params: dict) -> str:
    """Fetch customer order context for refund-email HITL flows."""
    customer_name = (
        params.get("customer_name")
        or params.get("customerName")
        or params.get("customer")
        or ""
    ).strip()
    order_ref = str(
        params.get("order_ref")
        or params.get("order_number")
        or params.get("orderNumber")
        or ""
    ).strip()

    if not customer_name:
        return (
            "Error: refund_order_context requires params_json with customer_name. "
            'Example: {"customer_name":"John Smith","order_ref":"1"}'
        )

    order_filter = ""
    try:
        if order_ref:
            order_filter = f"AND ranked.customerOrderNumber = {int(order_ref)}"
    except ValueError:
        order_filter = ""

    sql = f"""
WITH customer_match AS (
    SELECT
        id,
        firstName || ' ' || lastName AS customerName
    FROM Customer
    WHERE lower(firstName || ' ' || lastName) = lower('{_sql_string(customer_name)}')
),
ranked_orders AS (
    SELECT
        o.id,
        o.customerId,
        o.orderDate,
        o.status,
        ROUND(o.totalAmount, 2) AS totalAmount,
        ROW_NUMBER() OVER (PARTITION BY o.customerId ORDER BY o.orderDate ASC) AS customerOrderNumber
    FROM "Order" o
    WHERE o.status != 'Cancelled'
)
SELECT
    cm.customerName,
    ranked.customerOrderNumber,
    ranked.orderDate,
    ranked.status,
    ranked.totalAmount,
    GROUP_CONCAT(DISTINCT p.name) AS productNames
FROM customer_match cm
JOIN ranked_orders ranked ON ranked.customerId = cm.id
JOIN OrderItem oi ON oi.orderId = ranked.id
JOIN Product p ON p.id = oi.productId
WHERE 1 = 1
  {order_filter}
GROUP BY
    cm.customerName,
    ranked.customerOrderNumber,
    ranked.orderDate,
    ranked.status,
    ranked.totalAmount
ORDER BY ranked.orderDate DESC
LIMIT 1
""".strip()

    result = await _run_query(sql)
    if result == "Query returned no results.":
        return f"No matching order context found for {customer_name}."
    return result


async def _run_low_stock(params: dict) -> str:
    """Fetch products below a stock threshold (default 10)."""
    threshold = 10
    try:
        threshold = int(params.get("threshold", 10))
    except (ValueError, TypeError):
        pass

    sql = f"""
SELECT
    p.name,
    p.category,
    i.stockLevel,
    i.lastRestock
FROM Inventory i
JOIN Product p ON i.productId = p.id
WHERE i.stockLevel < {threshold}
ORDER BY i.stockLevel ASC
""".strip()

    return await _run_query(sql)


@tool
async def query_library(query_name: str, params_json: str = "{}") -> str:
    """Execute a pre-built SQL query from the library by name.
    Preferred over sql_query — faster and more reliable. NEVER call query_library('list').

    AVAILABLE QUERIES (use these names directly):
      Sales: total_revenue, revenue_by_month, revenue_by_category, sales_last_7d, sales_last_30d,
             sales_last_90d, aov_by_month, revenue_share_by_category (all-time),
             revenue_by_category_30d, revenue_by_category_90d
      Products: top_products_by_revenue, top_products_by_quantity, products_by_category,
                top_rated_products, products_without_reviews, top_products_with_share,
                high_rated_low_sales
      Inventory: low_stock, out_of_stock, inventory_overview, stockout_risk
      Orders: orders_by_status, recent_orders, orders_today, pending_orders, cancelled_order_rate
      Customers: top_customers_by_spend, new_customers_this_month, customer_count,
                 customers_with_most_orders, customer_segments
      Reviews: rating_distribution, recent_reviews, worst_rated_products
      API: api_usage_last_30_days, api_usage_summary
      Suppliers/POs: suppliers, purchase_orders, sales_velocity, replenishment_candidates,
                     reorder_with_cost
      HITL helpers: refund_order_context (requires params_json with customer_name; optional order_ref)
      Prospecting: business_health_snapshot, opportunity_matrix, automation_candidates

    SELECTION HINTS:
    - Revenue by category with share / percent -> revenue_share_by_category
    - Stockout risk / days of cover → stockout_risk (NOT low_stock)
    - Low stock / below threshold → low_stock (default < 10; pass params_json={"threshold": N} for custom threshold, e.g. "stock below 20" → params_json='{"threshold": 20}')
    - Revenue for specific period → revenue_by_category_30d, revenue_by_category_90d, sales_last_7d, etc.
    - Refund or dispute email context -> refund_order_context before falling back to sql_query
    - Typical plans: simple question = 1 call, complex analysis = 2 calls, HITL = 2 calls max
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

    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError:
        return "Error: params_json must be valid JSON."

    # Phase 3.2: Check cache
    cache_key = f"{query_name.strip()}::{json.dumps(params, sort_keys=True)}"
    cached = _QL_CACHE.get(cache_key)
    if cached and (time.time() - cached[0]) < _QL_CACHE_TTL:
        return cached[1]

    if query_name.strip() == "refund_order_context":
        result = await _run_refund_order_context(params)
        _QL_CACHE[cache_key] = (time.time(), result)
        return result

    if query_name.strip() == "low_stock":
        result = await _run_low_stock(params)
        _QL_CACHE[cache_key] = (time.time(), result)
        return result

    result = await _run_query(entry["sql"])

    # Inject computed date range so the LLM sees real dates
    days = entry.get("date_range_days")
    if days:
        end = datetime.date.today()
        start = end - datetime.timedelta(days=days)
        prefix = f"_Date range: {start.strftime('%b %d, %Y')} – {end.strftime('%b %d, %Y')} ({days} days)_\n\n"
        result = prefix + result

    _QL_CACHE[cache_key] = (time.time(), result)
    return result

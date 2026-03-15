import datetime
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
      Prospecting: business_health_snapshot, opportunity_matrix, automation_candidates

    SELECTION HINTS:
    - Stockout risk / days of cover → stockout_risk (NOT low_stock)
    - Low stock / below threshold → low_stock
    - Revenue for specific period → revenue_by_category_30d, revenue_by_category_90d, sales_last_7d, etc.
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

    result = _run_query(entry["sql"])

    # Inject computed date range so the LLM sees real dates
    days = entry.get("date_range_days")
    if days:
        end = datetime.date.today()
        start = end - datetime.timedelta(days=days)
        prefix = f"_Date range: {start.strftime('%b %d, %Y')} – {end.strftime('%b %d, %Y')} ({days} days)_\n\n"
        result = prefix + result

    return result

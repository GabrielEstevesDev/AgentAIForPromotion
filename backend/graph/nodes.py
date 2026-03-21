"""Node functions and Runnable chains for the AgenticStack StateGraph."""

import json
import logging
import re
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt

from ..config import LLM_MODEL, OPENAI_API_KEY
from ..core.mode_templates import MODE_TEMPLATES
from ..core.system_prompt import SYSTEM_PROMPT
from ..mode_classifier import classify_mode, match_direct_query
from ..tools import ALL_TOOLS
from ..validators import (
    check_summary_breakdown_coherence,
    normalize_empty_po_hitl_response,
    validate_hitl_structure,
)

logger = logging.getLogger(__name__)

# Keywords that indicate PO/replenishment intent
_PO_KEYWORDS = re.compile(
    r"(purchase\s*order|replenish|restock|reorder|low\s*stock|supplier|PO\b)",
    re.IGNORECASE,
)

_REFUND_EMAIL_PATTERN = re.compile(
    r"(refund|dispute|complaint).*(email|draft)|draft.*(refund|dispute|complaint).*(email)?",
    re.IGNORECASE,
)

_PO_DRAFT_PATTERN = re.compile(
    r"(purchase\s*order|create\s+a?\s*PO\b|create\s+(a\s+)?purchase\s*order|replenish|restock|reorder)",
    re.IGNORECASE,
)

# ── Direct chart patterns ──
# IMPORTANT: These must be SPECIFIC and UNAMBIGUOUS. If a prompt mixes concepts
# (e.g. "inventory for top products"), it should fall through to the LLM path
# which can reason about the right query + chart combination.
_CHART_REVENUE_BY_CATEGORY_PATTERN = re.compile(
    r"^[^.]*revenue\s+by\s+category[^.]*$", re.IGNORECASE | re.MULTILINE,
)
_CHART_REVENUE_TREND_PATTERN = re.compile(
    r"^[^.]*(monthly\s+revenue\s+trend|revenue\s+trend|sales\s+trend|revenue\s+by\s+month)[^.]*$",
    re.IGNORECASE | re.MULTILINE,
)
_CHART_PIE_CATEGORY_PATTERN = re.compile(r"pie\s+chart.*category", re.IGNORECASE)
_CHART_TOP_PRODUCTS_PATTERN = re.compile(
    r"^[^.]*(top\s+\d*\s*products?(\s+(by\s+)?(revenue|sales|quantity|chart|graph))?|best\s+sell)[^.]*$",
    re.IGNORECASE | re.MULTILINE,
)
_CHART_INVENTORY_PATTERN = re.compile(
    r"^[^.]*(inventory|stock)\s+(level|overview|by\s+category|per\s+category|chart|graph)[^.]*$",
    re.IGNORECASE | re.MULTILINE,
)
_CHART_ORDERS_STATUS_PATTERN = re.compile(
    r"^[^.]*orders?\s+(by\s+)?status[^.]*$", re.IGNORECASE | re.MULTILINE,
)
_CHART_RATING_PATTERN = re.compile(r"rating\s+distribution", re.IGNORECASE)
_CHART_CUSTOMER_SEG_PATTERN = re.compile(r"customer\s+segment", re.IGNORECASE)
_CHART_AOV_PATTERN = re.compile(
    r"(aov|average\s+order\s+value)\s+(trend|chart|graph|by\s+month)", re.IGNORECASE,
)
_CHART_TOP_BY_INVENTORY_PATTERN = re.compile(
    r"top\s+\d+\s+products?\s+(by\s+)?(inventory|stock)",
    re.IGNORECASE,
)

_CALC_PATTERN = re.compile(
    r"(total\s+price|sum\s+of|add\s+up|what\s+is\s+the\s+total|how\s+much\s+in\s+total"
    r"|combined\s+cost|total\s+cost|total\s+revenue\s+from)",
    re.IGNORECASE,
)

# Message injected when forcing the agent to stop calling tools
_STOP_TOOLS_MSG = (
    "You have reached your tool call limit. You MUST immediately produce your "
    "final text response using ONLY the data you have already gathered. "
    "If the user's request requires a HITL_REQUEST (email, strategy, purchase order), "
    "output the HITL_REQUEST JSON block now. Otherwise, write your analysis and answer. "
    "Keep your response concise."
)

# ---------------------------------------------------------------------------
# Shared LLM instances (built once, reused)
# max_tokens=2500 is a ceiling — actual output length is controlled by mode instruction
# Phase 2.1: with_retry + with_fallbacks for production resilience
# ---------------------------------------------------------------------------

_primary = ChatOpenAI(
    model=LLM_MODEL,
    temperature=0,
    timeout=60,
    max_tokens=2500,
    api_key=OPENAI_API_KEY,
)

_fallback = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    timeout=60,
    max_tokens=2500,
    api_key=OPENAI_API_KEY,
)

_llm_with_tools = (
    _primary.bind_tools(ALL_TOOLS)
    .with_fallbacks([_fallback.bind_tools(ALL_TOOLS)])
    .with_retry(stop_after_attempt=2)
)

_llm_no_tools = (
    _primary
    .with_fallbacks([_fallback])
    .with_retry(stop_after_attempt=2)
)

# Cheap model for conversation summarization (Phase 3.1)
_llm_summarizer = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    timeout=30,
    max_tokens=300,
    api_key=OPENAI_API_KEY,
)


def _build_control_tags(user_text: str, mode_name: str) -> list[str]:
    """Inject short control tags instead of growing the system prompt."""
    tags: list[str] = []
    text = user_text.lower()

    if any(token in text for token in ("% share", "percentage share", "percent", "share")):
        tags.append("REQUIRE_SHARE_COLUMNS")

    if "policy" in text or "knowledge base" in text or "guideline" in text:
        tags.append("REQUIRE_POLICY_SECTION")

    if any(token in text for token in ("revenue", "sales", "category", "orders", "stock", "inventory")):
        tags.append("REQUIRE_DATA_SECTION")

    if mode_name == "chart":
        tags.append("REQUIRE_PYTHON_EXECUTOR")

    if mode_name == "web":
        tags.append("USE_WEB_SEARCH_ONLY")

    if mode_name == "rag":
        tags.append("ANSWER_FROM_RAG_ONLY")

    if _CALC_PATTERN.search(user_text):
        tags.append("REQUIRE_SQL_FOR_CALCULATIONS")

    if mode_name == "hitl":
        tags.append("REQUIRE_HITL_JSON_ONLY")
        if _REFUND_EMAIL_PATTERN.search(user_text):
            tags.extend([
                "USE_QUERY_LIBRARY_REFUND_CONTEXT",
                "REQUIRE_PRODUCT_NAMES",
                "REQUIRE_TOTAL_REFUND_AMOUNT",
            ])
        if _PO_DRAFT_PATTERN.search(user_text):
            tags.extend([
                "NO_PREAPPROVAL_PO_TOOL",
                "NO_HITL_IF_NO_REORDER",
                "FIXED_SUPPLIER_ECOSOURCE",
            ])

    return tags


def _match_chart_request(user_text: str) -> str:
    """Route simple chart requests to deterministic handlers.

    Only matches clear, unambiguous requests. If the prompt mixes concepts
    (e.g. "inventory for top products", "revenue trend by category"),
    returns "" so the LLM handles it with proper reasoning.
    """
    lower = user_text.lower()

    # Conflict detection: count how many concept groups are mentioned.
    # If 2+ groups match, the request is ambiguous → let LLM handle it.
    # "top N products by inventory/stock" is a single concept — not a conflict
    if _CHART_TOP_BY_INVENTORY_PATTERN.search(user_text):
        return "top_products_by_inventory"

    concept_groups = [
        any(w in lower for w in ("inventory", "stock level", "stock overview")),
        any(w in lower for w in ("top product", "best sell", "top 5", "top 10", "top 15", "top 20")),
        any(w in lower for w in ("revenue by category", "category revenue", "category share")),
        any(w in lower for w in ("revenue trend", "sales trend", "revenue by month", "monthly revenue", "and trend")),
        any(w in lower for w in ("order status", "orders by status")),
        any(w in lower for w in ("rating distribution",)),
        any(w in lower for w in ("customer segment",)),
        any(w in lower for w in ("aov", "average order value")),
    ]
    if sum(concept_groups) >= 2:
        logger.info("Chart request has mixed concepts — routing to LLM")
        return ""

    if _CHART_PIE_CATEGORY_PATTERN.search(user_text):
        return "revenue_by_category_30d"
    if _CHART_REVENUE_BY_CATEGORY_PATTERN.search(user_text):
        return "revenue_by_category_30d"
    if _CHART_REVENUE_TREND_PATTERN.search(user_text):
        return "revenue_by_month"
    if _CHART_INVENTORY_PATTERN.search(user_text):
        return "inventory_overview"
    if _CHART_TOP_PRODUCTS_PATTERN.search(user_text):
        return "top_products_by_revenue"
    if _CHART_ORDERS_STATUS_PATTERN.search(user_text):
        return "orders_by_status"
    if _CHART_RATING_PATTERN.search(user_text):
        return "rating_distribution"
    if _CHART_CUSTOMER_SEG_PATTERN.search(user_text):
        return "customer_segments"
    if _CHART_AOV_PATTERN.search(user_text):
        return "aov_by_month"
    return ""


def _extract_date_range_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("_Date range:"):
            return stripped.strip("_")
    return ""


def _parse_markdown_table(text: str) -> list[dict[str, str]]:
    """Parse the first markdown table in a tool result."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index in range(len(lines) - 1):
        if not lines[index].startswith("|") or not lines[index + 1].startswith("|"):
            continue
        if "---" not in lines[index + 1]:
            continue
        headers = [cell.strip() for cell in lines[index].strip("|").split("|")]
        rows: list[dict[str, str]] = []
        cursor = index + 2
        while cursor < len(lines) and lines[cursor].startswith("|"):
            cells = [cell.strip() for cell in lines[cursor].strip("|").split("|")]
            if len(cells) == len(headers):
                rows.append(dict(zip(headers, cells, strict=False)))
            cursor += 1
        return rows
    return []


def _to_float(value: str) -> float:
    cleaned = value.replace("$", "").replace(",", "").strip()
    return float(cleaned)


def _clean_chart_output(output: str) -> str:
    return output.split("\n\n[CHART GENERATED", 1)[0].strip()


async def _build_generic_chart(
    query_name: str,
    title: str,
    chart_type: str,
    x_col: str,
    y_col: str,
    color: str = "#14532d",
    figsize: tuple = (10, 5),
    x_rotation: int = 30,
    limit: int | None = None,
) -> str:
    """Generic chart builder: query → parse → matplotlib → response.

    chart_type: "bar", "hbar", "line", "pie"
    """
    from ..tools.python_tool import python_executor as _py_tool
    from ..tools.query_library import query_library as _ql_tool

    result = await _ql_tool.ainvoke({"query_name": query_name})
    rows = _parse_markdown_table(result)
    if not rows:
        return f"### {title}\n\nNo data available for this chart."

    if limit:
        rows = rows[:limit]

    x_vals = [row.get(x_col, "") for row in rows]
    y_raw = [row.get(y_col, "0") for row in rows]
    try:
        y_vals = [_to_float(v) for v in y_raw]
    except (ValueError, TypeError):
        y_vals = list(range(len(x_vals)))

    code_lines = [
        "import matplotlib.pyplot as plt",
        f"x = {json.dumps(x_vals)}",
        f"y = {json.dumps(y_vals)}",
        "plt.style.use('seaborn-v0_8-whitegrid')",
        f"fig, ax = plt.subplots(figsize={figsize})",
    ]

    if chart_type == "bar":
        code_lines.append(f"ax.bar(x, y, color='{color}')")
        code_lines.append(f"ax.set_xlabel('{x_col.replace('_', ' ').title()}')")
        code_lines.append(f"ax.set_ylabel('{y_col.replace('_', ' ').title()}')")
        code_lines.append(f"ax.tick_params(axis='x', rotation={x_rotation})")
    elif chart_type == "hbar":
        code_lines.append(f"ax.barh(x, y, color='{color}')")
        code_lines.append(f"ax.set_xlabel('{y_col.replace('_', ' ').title()}')")
        code_lines.append("ax.invert_yaxis()")
    elif chart_type == "line":
        code_lines.append(f"ax.plot(x, y, marker='o', linewidth=2, color='{color}')")
        code_lines.append(f"ax.set_xlabel('{x_col.replace('_', ' ').title()}')")
        code_lines.append(f"ax.set_ylabel('{y_col.replace('_', ' ').title()}')")
        code_lines.append(f"ax.tick_params(axis='x', rotation={x_rotation})")
    elif chart_type == "pie":
        code_lines.append("ax.pie(y, labels=x, autopct='%1.1f%%', startangle=140)")
        code_lines.append("ax.axis('equal')")

    code_lines.append(f"ax.set_title('{title}')")
    code_lines.append("plt.tight_layout()")

    chart_output = await _py_tool.ainvoke({"code": "\n".join(code_lines)})
    chart_markdown = _clean_chart_output(chart_output)

    # Auto-generate insight from top value
    top_x = x_vals[0] if x_vals else "N/A"
    top_y = y_vals[0] if y_vals else 0

    return (
        f"### {title}\n\n"
        f"{chart_markdown}\n\n"
        f"**Insight:** {top_x} leads with {top_y:,.0f}.\n\n"
        f"**Action:** Focus attention on top and bottom performers to optimize outcomes."
    )


async def _build_category_chart_response() -> str:
    from ..tools.python_tool import python_executor as _py_tool
    from ..tools.query_library import query_library as _ql_tool

    result = await _ql_tool.ainvoke({"query_name": "revenue_by_category_30d"})
    rows = _parse_markdown_table(result)
    if not rows:
        return "### Revenue by Category (Last 30 Days)\n\nNo chart data was available."

    categories = [row["category"] for row in rows]
    revenues = [_to_float(row["revenue"]) for row in rows]
    shares = [_to_float(row["revenue_share_pct"]) for row in rows if row.get("revenue_share_pct")]
    date_range = _extract_date_range_line(result)

    code = (
        "import matplotlib.pyplot as plt\n"
        f"categories = {json.dumps(categories)}\n"
        f"revenues = {json.dumps(revenues)}\n"
        "plt.style.use('seaborn-v0_8-whitegrid')\n"
        "fig, ax = plt.subplots(figsize=(10, 5))\n"
        "ax.bar(categories, revenues, color='#14532d')\n"
        "ax.set_title('Revenue by Category - Last 30 Days')\n"
        "ax.set_xlabel('Category')\n"
        "ax.set_ylabel('Revenue ($)')\n"
        "ax.tick_params(axis='x', rotation=30)\n"
        "plt.tight_layout()\n"
    )
    chart_output = await _py_tool.ainvoke({"code": code})
    chart_markdown = _clean_chart_output(chart_output)

    top_category = categories[0]
    top_revenue = revenues[0]
    top_share = shares[0] if shares else 0.0
    context_line = date_range or "Revenue by category for the last 30 days."

    return (
        "### Revenue by Category (Last 30 Days)\n\n"
        f"{context_line}\n\n"
        f"{chart_markdown}\n\n"
        f"**Insight:** {top_category} leads category revenue at ${top_revenue:,.2f} and "
        f"{top_share:.1f}% share.\n\n"
        f"**Action:** Prioritize the next promotion or merchandising test in {top_category} first."
    )


async def _build_revenue_trend_chart_response() -> str:
    from ..tools.python_tool import python_executor as _py_tool
    from ..tools.query_library import query_library as _ql_tool

    result = await _ql_tool.ainvoke({"query_name": "revenue_by_month"})
    rows = _parse_markdown_table(result)
    if not rows:
        return "### Monthly Revenue Trend\n\nNo chart data was available."

    months = [row["month"] for row in rows]
    revenues = [_to_float(row["revenue"]) for row in rows]

    code = (
        "import matplotlib.pyplot as plt\n"
        f"months = {json.dumps(months)}\n"
        f"revenues = {json.dumps(revenues)}\n"
        "plt.style.use('seaborn-v0_8-whitegrid')\n"
        "fig, ax = plt.subplots(figsize=(10, 5))\n"
        "ax.plot(months, revenues, marker='o', linewidth=2, color='#1d4ed8')\n"
        "ax.set_title('Monthly Revenue Trend')\n"
        "ax.set_xlabel('Month')\n"
        "ax.set_ylabel('Revenue ($)')\n"
        "ax.tick_params(axis='x', rotation=30)\n"
        "plt.tight_layout()\n"
    )
    chart_output = await _py_tool.ainvoke({"code": code})
    chart_markdown = _clean_chart_output(chart_output)

    latest = revenues[-1]
    prior = revenues[-2] if len(revenues) > 1 else revenues[-1]
    trend_word = "up" if latest >= prior else "down"

    return (
        "### Monthly Revenue Trend\n\n"
        "Revenue by month for the last 12 months.\n\n"
        f"{chart_markdown}\n\n"
        f"**Insight:** Revenue is {trend_word} in the latest month at ${latest:,.2f} versus ${prior:,.2f} in the prior month.\n\n"
        "**Action:** Investigate the latest month drivers and replicate the strongest category or campaign pattern."
    )


def _augment_config(config: dict, state: dict) -> dict:
    """Merge graph state values into the config's configurable dict.

    We shallow-copy only the configurable dict (not deepcopy the whole config)
    because the runtime config may contain unpicklable async objects.
    """
    if not config:
        config = {}
    augmented = dict(config)
    augmented["configurable"] = dict(config.get("configurable", {}))
    augmented["configurable"]["po_intent"] = state.get("po_intent", False)
    augmented["configurable"]["hitl_approved"] = state.get("hitl_approved", False)
    return augmented


# ---------------------------------------------------------------------------
# Node: summarize_if_needed (Phase 3.1 — condense long conversations)
# ---------------------------------------------------------------------------

_SUMMARIZE_THRESHOLD = 12  # messages before summarization kicks in
_KEEP_RECENT = 6           # keep last N messages verbatim


async def summarize_if_needed(state: dict) -> dict:
    """Summarize older messages when conversation grows too long."""
    from langchain_core.messages import RemoveMessage

    messages = state.get("messages", [])
    if len(messages) <= _SUMMARIZE_THRESHOLD:
        return {}

    # Split: older messages to summarize, recent to keep
    older = messages[:-_KEEP_RECENT]
    if not older:
        return {}

    # Build a summary of older messages
    summary_input = []
    for msg in older:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        # Truncate very long messages for the summary
        if len(content) > 500:
            content = content[:500] + "..."
        summary_input.append(f"{role}: {content}")

    summary_prompt = (
        "Summarize this conversation history in 2-3 sentences. "
        "Focus on key questions asked, data retrieved, and decisions made:\n\n"
        + "\n".join(summary_input)
    )

    try:
        t0 = time.perf_counter()
        response = await _llm_summarizer.ainvoke([{"role": "user", "content": summary_prompt}])
        dur = time.perf_counter() - t0
        logger.info("PERF_LOG: [Conversation Summarization] - %.3fs (%d msgs -> summary)", dur, len(older))

        summary_text = response.content if isinstance(response.content, str) else str(response.content)

        # Remove old messages and prepend summary as SystemMessage
        removals = [RemoveMessage(id=msg.id) for msg in older if msg.id]
        summary_msg = SystemMessage(content=f"[Conversation summary]: {summary_text}")

        return {
            "messages": removals + [summary_msg],
            "summary": summary_text,
        }
    except Exception as e:
        logger.warning("Summarization failed, continuing with full history: %s", e)
        return {}


# ---------------------------------------------------------------------------
# Node: classify (function node — no LLM call, no streaming needed)
# ---------------------------------------------------------------------------

def classify(state: dict) -> dict:
    """Classify the user message into a response mode and detect intents."""
    messages = state["messages"]

    # Find the last human message
    last_human = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_human = msg
            break

    if not last_human:
        return {}

    user_text = last_human.content if isinstance(last_human.content, str) else str(last_human.content)

    # Phase 1.4: Try direct query routing first (skip LLM entirely)
    direct_query_name = match_direct_query(user_text)
    direct_chart_name = ""

    # Classify mode
    t0 = time.perf_counter()
    mode = classify_mode(user_text)
    classify_dur = time.perf_counter() - t0
    logger.info("PERF_LOG: [Mode Classification] - %.4fs", classify_dur)

    if direct_query_name:
        logger.info("Mode: direct_query -> %s (skipping LLM)", direct_query_name)
    else:
        logger.info("Mode: %s (max_tools=%d)", mode.name, mode.max_tool_calls)

    if mode.name == "chart":
        direct_chart_name = _match_chart_request(user_text)
        if direct_chart_name:
            logger.info("Direct chart route -> %s", direct_chart_name)

    # Detect HITL approval
    msg_lower = user_text.lower()
    is_hitl_approval = "[hitl response]" in msg_lower and "approve" in msg_lower

    # Detect PO intent (sticky — once set, stays True)
    po_intent = state.get("po_intent", False)
    if _PO_KEYWORDS.search(user_text):
        po_intent = True

    control_tags = _build_control_tags(user_text, mode.name)
    control_block = ""
    if control_tags:
        control_block = f"\n[CONTROL_TAGS] {' '.join(control_tags)}"

    # Prepend mode instruction to the user message.
    augmented_content = f"{mode.mode_instruction}{control_block}\n\n{user_text}"
    augmented_msg = HumanMessage(content=augmented_content, id=last_human.id)

    return {
        "messages": [augmented_msg],
        "mode": "direct_query" if direct_query_name else mode.name,
        "mode_config": {
            "max_tokens": mode.max_tokens,
            "max_tool_calls": mode.max_tool_calls,
            "mode_instruction": mode.mode_instruction,
        },
        "direct_query_name": direct_query_name or "",
        "direct_chart_name": direct_chart_name,
        "tool_call_count": 0,
        "po_intent": po_intent,
        "hitl_approved": is_hitl_approval,
        "needs_hitl": False,
        "hitl_payload": None,
        "hitl_decision": state.get("hitl_decision"),
        "captured_sqls": [],
        "response_text": "",
    }


# ---------------------------------------------------------------------------
# Node: fast_response (greeting fast lane — no LLM call)
# ---------------------------------------------------------------------------

_GREETING_RESPONSES = {
    "hello": "Hello! I'm AgenticStack, your e-commerce assistant. How can I help you today?",
    "hi": "Hello! I'm AgenticStack, your e-commerce assistant. How can I help you today?",
    "hey": "Hey! I'm AgenticStack, your e-commerce assistant. How can I help you today?",
    "thanks": "You're welcome! Let me know if you need anything else.",
    "thank you": "You're welcome! Let me know if you need anything else.",
    "ok": "Got it! Let me know if you need anything else.",
    "okay": "Got it! Let me know if you need anything else.",
    "got it": "Got it! Let me know if you need anything else.",
    "sure": "Sure thing! What would you like to do next?",
    "who are you": "I'm AgenticStack, an AI-powered e-commerce assistant. I can analyze sales data, search our knowledge base, create charts, and manage purchase orders with approval workflows.",
    "what can you do": "I'm AgenticStack, an AI-powered e-commerce assistant. I can analyze sales data, search our knowledge base, create charts, and manage purchase orders with approval workflows.",
    "what are you": "I'm AgenticStack, an AI-powered e-commerce assistant. I can analyze sales data, search our knowledge base, create charts, and manage purchase orders with approval workflows.",
}
_GREETING_DEFAULT = "Hello! I'm AgenticStack, your e-commerce assistant. How can I help you today?"
_OFF_TOPIC_RESPONSE = (
    "I'm focused on the e-commerce demo workspace. Ask me about sales, products, "
    "orders, inventory, policies, charts, or approval workflows."
)


def fast_response(state: dict) -> dict:
    """Return a hardcoded response for greetings. No LLM call."""
    if state.get("mode") == "off_topic":
        return {
            "messages": [AIMessage(content=_OFF_TOPIC_RESPONSE)],
            "response_text": _OFF_TOPIC_RESPONSE,
        }

    messages = state["messages"]
    last_human = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_human = msg
            break

    user_text = ""
    if last_human:
        content = last_human.content if isinstance(last_human.content, str) else str(last_human.content)
        # Strip the mode instruction prefix that classify prepended
        if "\n\n" in content:
            user_text = content.split("\n\n", 1)[1].strip().lower().rstrip("?!.")
        else:
            user_text = content.strip().lower().rstrip("?!.")

    response_text = _GREETING_RESPONSES.get(user_text, _GREETING_DEFAULT)
    return {
        "messages": [AIMessage(content=response_text)],
        "response_text": response_text,
    }


# ---------------------------------------------------------------------------
# Node: direct_query (Phase 1.4 — skip LLM for simple factual queries)
# ---------------------------------------------------------------------------

async def direct_query(state: dict) -> dict:
    """Execute a pre-matched query_library entry directly — no LLM call."""
    query_name = state.get("direct_query_name", "")
    if not query_name:
        return {"response_text": ""}

    from ..tools.query_library import query_library as _ql_tool
    result = await _ql_tool.ainvoke({"query_name": query_name})

    title_map = {
        "total_revenue": "Total Revenue",
        "revenue_share_by_category": "Revenue by Category with Share",
        "top_products_by_revenue": "Top Products by Revenue",
    }
    title = title_map.get(query_name, query_name.replace("_", " ").title())
    response_text = f"### {title}\n\n{result}"
    return {
        "messages": [AIMessage(content=response_text)],
        "response_text": response_text,
    }


async def direct_chart(state: dict) -> dict:
    """Build common charts deterministically without an LLM planning step."""
    chart_name = state.get("direct_chart_name", "")
    if not chart_name:
        return {"response_text": ""}

    # Specialized builders (custom insight text)
    if chart_name == "revenue_by_category_30d":
        response_text = await _build_category_chart_response()
    elif chart_name == "revenue_by_month":
        response_text = await _build_revenue_trend_chart_response()
    # Generic builders
    elif chart_name == "top_products_by_revenue":
        response_text = await _build_generic_chart(
            "top_products_by_revenue", "Top Products by Revenue",
            "hbar", "name", "revenue", color="#1d4ed8", limit=15,
        )
    elif chart_name == "inventory_overview":
        response_text = await _build_generic_chart(
            "inventory_overview", "Inventory Overview by Category",
            "bar", "category", "total_units", color="#14532d",
        )
    elif chart_name == "orders_by_status":
        response_text = await _build_generic_chart(
            "orders_by_status", "Orders by Status",
            "pie", "status", "count",
        )
    elif chart_name == "rating_distribution":
        response_text = await _build_generic_chart(
            "rating_distribution", "Rating Distribution",
            "bar", "rating", "count", color="#d97706", x_rotation=0,
        )
    elif chart_name == "customer_segments":
        response_text = await _build_generic_chart(
            "customer_segments", "Customer Segments",
            "pie", "segment", "customers",
        )
    elif chart_name == "aov_by_month":
        response_text = await _build_generic_chart(
            "aov_by_month", "Average Order Value Trend",
            "line", "month", "aov", color="#1d4ed8",
        )
    elif chart_name == "top_products_by_inventory":
        # Extract N from user message
        limit = 15  # default
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, HumanMessage):
                text = msg.content if isinstance(msg.content, str) else str(msg.content)
                n_match = re.search(r"top\s+(\d+)", text, re.IGNORECASE)
                if n_match:
                    limit = min(int(n_match.group(1)), 50)
                break
        response_text = await _build_generic_chart(
            "top_products_by_inventory", f"Top {limit} Products by Stock Level",
            "hbar", "name", "stockLevel", color="#14532d", limit=limit,
        )
    else:
        response_text = ""

    return {
        "messages": [AIMessage(content=response_text)],
        "response_text": response_text,
    }


# ---------------------------------------------------------------------------
# Node: plan_and_call (Runnable chain — LLM is streamable)
# ---------------------------------------------------------------------------

def _plan_preprocess(state: dict) -> list:
    """Extract messages from state with system prompt prepended.

    Two separate SystemMessages enable OpenAI prompt prefix caching:
    the core prompt (always identical) is cached across requests.
    """
    msgs = [SystemMessage(content=SYSTEM_PROMPT)]
    mode = state.get("mode", "factual")
    template = MODE_TEMPLATES.get(mode, "")
    if template:
        msgs.append(SystemMessage(content=template))
    msgs.extend(state["messages"])
    return msgs


def _wrap_response(response) -> dict:
    """Wrap LLM response in state update format."""
    return {"messages": [response]}


# Runnable chain: state → messages → LLM (with tools) → state update
# LangGraph can stream through the LLM because it's a Runnable in the chain
plan_and_call = RunnableLambda(_plan_preprocess) | _llm_with_tools | RunnableLambda(_wrap_response)


# ---------------------------------------------------------------------------
# Node: execute_tools
# ---------------------------------------------------------------------------

_tool_node = ToolNode(ALL_TOOLS)


async def execute_tools(state: dict, config: RunnableConfig) -> dict:
    """Execute tool calls from the last AI message and track SQL captures."""
    # Augment config with state values so tools can check po_intent / hitl_approved
    augmented_config = _augment_config(config, state)

    # Phase 2.3: Graceful tool degradation — catch tool errors so LLM can work around them
    try:
        result = await _tool_node.ainvoke(state, config=augmented_config)
    except Exception as exc:
        logger.warning("Tool execution failed, injecting error message: %s", exc)
        # Find tool call IDs from the last AI message to create proper ToolMessages
        messages = state.get("messages", [])
        last_ai = messages[-1] if messages else None
        error_msgs = []
        if last_ai and hasattr(last_ai, "tool_calls"):
            for tc in last_ai.tool_calls:
                error_msgs.append(ToolMessage(
                    content=f"Tool error: {exc}. Please respond with available data.",
                    tool_call_id=tc.get("id", ""),
                ))
        result = {"messages": error_msgs} if error_msgs else {"messages": []}

    # Count tool calls from the last AI message
    messages = state["messages"]
    last_ai = messages[-1] if messages else None
    num_calls = len(getattr(last_ai, "tool_calls", []) or []) if last_ai else 0

    new_tool_count = state.get("tool_call_count", 0) + num_calls

    # Capture SQL from sql_query tool calls
    new_sqls: list[str] = []
    if last_ai and hasattr(last_ai, "tool_calls"):
        for tc in last_ai.tool_calls:
            if tc.get("name") == "sql_query":
                args = tc.get("args", {})
                sql = args.get("query", "").strip() if isinstance(args, dict) else ""
                if sql:
                    new_sqls.append(sql)

    logger.info(
        "Tools executed: %d call(s), total=%d/%d",
        num_calls,
        new_tool_count,
        (state.get("mode_config") or {}).get("max_tool_calls", 5),
    )

    return {
        **result,
        "tool_call_count": new_tool_count,
        "captured_sqls": new_sqls,
    }


# ---------------------------------------------------------------------------
# Node: force_respond (Runnable chain — LLM without tools, streamable)
# ---------------------------------------------------------------------------

def _force_preprocess(state: dict) -> list:
    """Extract messages with system prompt + stop instruction."""
    logger.info("Forcing final response (tool limit reached)")
    msgs = [SystemMessage(content=SYSTEM_PROMPT)]
    mode = state.get("mode", "factual")
    template = MODE_TEMPLATES.get(mode, "")
    if template:
        msgs.append(SystemMessage(content=template))
    msgs.extend(state["messages"])

    stop_msg = _STOP_TOOLS_MSG
    # force_respond means LLM has no tools — if chart mode, extract actual chart URLs
    if mode == "chart":
        chart_urls = []
        for msg in state.get("messages", []):
            if isinstance(msg, ToolMessage) and isinstance(msg.content, str):
                urls = re.findall(r"!\[chart\]\(/api/charts/[^)]+\)", msg.content)
                chart_urls.extend(urls)
        if chart_urls:
            stop_msg += (
                f"\n\nCRITICAL: A chart was generated. You MUST include this exact markdown "
                f"in your response:\n{chart_urls[-1]}\n"
                "Do NOT output the raw data as a markdown table. "
                "Only the chart image, 1 Insight line, and 1 Action line."
            )
        else:
            stop_msg += (
                "\n\nIMPORTANT: If python_executor returned a chart URL "
                "like ![chart](/api/charts/...), include that EXACT URL once. "
                "Do NOT invent or fabricate any other image URLs."
            )
    msgs.append(SystemMessage(content=stop_msg))
    return msgs


# Runnable chain: state → messages → LLM (no tools) → state update
force_respond = RunnableLambda(_force_preprocess) | _llm_no_tools | RunnableLambda(_wrap_response)


# ---------------------------------------------------------------------------
# Node: extract_hitl
# ---------------------------------------------------------------------------

def extract_hitl(state: dict) -> dict:
    """Check if the last AI message contains a HITL_REQUEST JSON block."""
    messages = state["messages"]
    last_ai = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            last_ai = msg
            break

    if not last_ai:
        return {"needs_hitl": False, "hitl_payload": None}

    content = last_ai.content if isinstance(last_ai.content, str) else str(last_ai.content)

    normalized_response = normalize_empty_po_hitl_response(content)
    if normalized_response:
        logger.info("Skipping empty PO HITL card and returning plain replenishment status")
        return {
            "needs_hitl": False,
            "hitl_payload": None,
            "messages": [AIMessage(content=normalized_response)],
        }

    # Look for ```json blocks containing HITL_REQUEST
    json_blocks = re.findall(r"```json\s*\n(.*?)```", content, re.DOTALL)
    for block in json_blocks:
        try:
            parsed = json.loads(block.strip())
            if "HITL_REQUEST" in parsed:
                hitl = parsed["HITL_REQUEST"]
                logger.info("HITL_REQUEST detected in AI response")

                # Validate required HITL fields
                validation_errors = []
                if not hitl.get("evidence"):
                    validation_errors.append("empty evidence")
                if not hitl.get("artifacts_preview"):
                    validation_errors.append("empty artifacts_preview")
                if not hitl.get("actions") or len(hitl.get("actions", [])) < 2:
                    validation_errors.append("fewer than 2 actions")
                if not hitl.get("summary"):
                    validation_errors.append("empty summary")

                if validation_errors:
                    logger.warning("HITL_REQUEST validation failed: %s", ", ".join(validation_errors))
                    error_msg = (
                        "I encountered an issue generating the approval card. "
                        "Please try your request again."
                    )
                    return {
                        "needs_hitl": False,
                        "hitl_payload": None,
                        "messages": [AIMessage(content=error_msg)],
                    }

                return {"needs_hitl": True, "hitl_payload": hitl}
        except json.JSONDecodeError:
            continue

    return {"needs_hitl": False, "hitl_payload": None}


# ---------------------------------------------------------------------------
# Node: hitl_gate (Phase B — native interrupt)
# ---------------------------------------------------------------------------

def hitl_gate(state: dict) -> dict:
    """Pause the graph and wait for user approval via LangGraph interrupt."""
    payload = state.get("hitl_payload", {})
    logger.info("Graph interrupted at hitl_gate — waiting for user decision")

    # This call pauses the graph. It resumes when Command(resume=...) is sent.
    decision = interrupt(payload)

    action = decision.get("action", "approve")
    logger.info("Graph resumed with decision: %s", action)
    return {"hitl_decision": decision, "hitl_approved": action == "approve"}


# ---------------------------------------------------------------------------
# Node: inject_revision_request (injects changes instruction into state for plan_and_call)
# ---------------------------------------------------------------------------

def inject_revision_request(state: dict) -> dict:
    """Inject the user's revision request into messages so plan_and_call can handle it."""
    decision = state.get("hitl_decision", {})
    controls = decision.get("controls", {})
    notes = decision.get("notes", "")

    parts = [
        "[REVISION REQUESTED] The user wants changes to the draft above.",
        "You MUST revise the HITL_REQUEST to address every change below.",
        "Use tools if you need additional data (e.g. customer names, order details).",
        "Re-output the complete updated HITL_REQUEST JSON block.",
    ]
    if controls:
        parts.append(f"User controls: {json.dumps(controls)}")
    if notes:
        parts.append(f"User notes (MUST address these): {notes}")

    revision_msg = HumanMessage(content="\n".join(parts))
    return {"messages": [revision_msg], "tool_call_count": 0}


# ---------------------------------------------------------------------------
# Node: post_approve (Runnable chain for streaming)
# ---------------------------------------------------------------------------

def _approve_preprocess(state: dict) -> list:
    """Build messages for post-approval LLM call."""
    decision = state.get("hitl_decision", {})
    action = decision.get("action", "approve")
    controls = decision.get("controls", {})
    notes = decision.get("notes", "")

    if action == "request_changes":
        # Tell the LLM to REVISE the draft, not finalize it
        approval_parts = [
            "[HITL CHANGES REQUESTED] The user wants you to revise the draft.",
            "You MUST address every change the user requested and re-output an updated HITL_REQUEST JSON block.",
            "Use tools if you need additional data (e.g. customer names, order details).",
        ]
        if controls:
            approval_parts.append(f"User controls: {json.dumps(controls)}")
        if notes:
            approval_parts.append(f"User notes (MUST address these): {notes}")
    elif action == "reject":
        approval_parts = ["[HITL REJECTED] The user rejected this request. Acknowledge briefly."]
        if notes:
            approval_parts.append(f"User notes: {notes}")
    else:
        # approve
        approval_parts = [f"[HITL APPROVED] Action: {action}"]
        if controls:
            approval_parts.append(f"Controls: {json.dumps(controls)}")
        if notes:
            approval_parts.append(f"Notes: {notes}")

    approval_msg = HumanMessage(content="\n".join(approval_parts))

    msgs = [SystemMessage(content=SYSTEM_PROMPT)]
    mode = state.get("mode", "factual")
    template = MODE_TEMPLATES.get(mode, "")
    if template:
        msgs.append(SystemMessage(content=template))
    msgs.extend(state["messages"])
    msgs.append(approval_msg)
    return msgs


def _wrap_approve_response(response) -> dict:
    """Wrap post-approval response. Include approval context in messages."""
    return {"messages": [response]}


# Runnable chain for post-approval: state → messages → LLM (with tools) → state update
post_approve = RunnableLambda(_approve_preprocess) | _llm_with_tools | RunnableLambda(_wrap_approve_response)


# ---------------------------------------------------------------------------
# Node: assemble_response
# ---------------------------------------------------------------------------

def assemble_response(state: dict) -> dict:
    """Build the final response text with SQL prefix."""
    messages = state["messages"]

    # Find the last AI message
    last_ai = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            last_ai = msg
            break

    if not last_ai:
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                last_ai = msg
                break

    content = ""
    if last_ai:
        content = last_ai.content if isinstance(last_ai.content, str) else str(last_ai.content)

    # Prepend captured SQL blocks
    sqls = state.get("captured_sqls", [])
    if sqls:
        sql_prefix = ""
        for sql in sqls:
            sql_prefix += f"```sql\n{sql}\n```\n\n"
        content = sql_prefix + content

    return {"response_text": content}


# ---------------------------------------------------------------------------
# Node: validate
# ---------------------------------------------------------------------------

def validate(state: dict) -> dict:
    """Run post-processing validators on the assembled response."""
    response_text = state.get("response_text", "")

    normalized_response = normalize_empty_po_hitl_response(response_text)
    if normalized_response:
        response_text = normalized_response
        logger.info("Normalized empty PO HITL response into plain text")

    coherence_note = check_summary_breakdown_coherence(response_text)
    if coherence_note:
        response_text += coherence_note
        logger.info("Appended coherence note to response")

    hitl_warnings = validate_hitl_structure(response_text)
    if hitl_warnings:
        logger.warning("HITL validation warnings: %s", hitl_warnings)

    return {"response_text": response_text}

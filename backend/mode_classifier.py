"""Response-mode classifier for Aria.

Classifies user messages into response modes BEFORE the agent runs.
Each mode sets: max_tokens, max_tool_calls, and a mode-specific instruction
that is prepended to the system prompt for that request.
"""

import re
from dataclasses import dataclass

# ── Keyword patterns per mode ────────────────────────────────────────────────

_GREETING_PATTERN = re.compile(
    r"^(hello|hi|hey|thanks?(\s+you)?|thank\s+you|ok|okay|got\s+it|sure|"
    r"who\s+are\s+you|what\s+(can\s+you|are\s+you)\s+do|what\s+are\s+you)[\s?!.]*$",
    re.IGNORECASE,
)

_HITL_PATTERN = re.compile(
    r"((30[\s-]?day\s+)?promotion\s+strategy|campaign\s+(strategy|plan)"
    r"|draft\s+(a\s+)?refund\s+email|refund\s+email|dispute\s+email"
    r"|complaint\s+email|email\s+(to|for)\s+.*(refund|dispute|complaint)"
    r"|purchase\s*order|create\s+a?\s*PO\b|prepare\s+a?\s*PO\b"
    r"|create\s+(a\s+)?purchase\s*order|draft\s+(a\s+)?purchase\s*order"
    r"|\breplenish(ment)?\b|\brestock\b|\breorder\b)",
    re.IGNORECASE,
)

_CHART_PATTERN = re.compile(
    r"(chart|graph|plot|visuali[sz]|histogram|pie\s*chart|bar\s*chart|line\s*chart"
    r"|show\s+me\s+a\s+(chart|graph|plot)|trend\s*line)",
    re.IGNORECASE,
)

_PROSPECTING_PATTERN = re.compile(
    r"(use\s*case|pilot|prospect|demo\s+(for|to|scenario)|ROI\b|workflow\s*(map|automation)"
    r"|opportunity|what\s+can\s+(you|this|aria)\s+do|client|recommend.*AI"
    r"|AI\s+(for|in)\s+(commerce|retail|ecommerce|e-commerce)"
    r"|presales|discovery\s+assistant|sellable|transferable)",
    re.IGNORECASE,
)

_RAG_PATTERN = re.compile(
    r"(polic[yi]|return\s+polic|shipping\s+(polic|rule)|warranty|FAQ|knowledge\s*base"
    r"|internal\s+doc|guideline|procedure|support\s+guide|promotion\s+types?"
    r"|discount\s+strateg|bundle\s+promotions?"
    r"|guarantee|refund\s+polic|exchange\s+polic|repair\s+polic)",
    re.IGNORECASE,
)

_WEB_PATTERN = re.compile(
    r"(web\s+trends?|market\s+trends?|industry\s+trends?|competitor\s+analysis"
    r"|external\s+(data|trends?)|e-?commerce\s+trends?\s+\d{4}"
    r"|market\s+(research|landscape|overview)"
    r"|latest\s+.{0,30}trends?|top\s+.{0,20}platforms?\s+in\s+\d{4})",
    re.IGNORECASE,
)

_DATA_REQUEST_PATTERN = re.compile(
    r"(revenue|sales|order|category|product|inventory|stock|customer|segment|aov|rating|units?)",
    re.IGNORECASE,
)

_OFF_TOPIC_PATTERN = re.compile(
    r"(capital\s+of|prime\s+minister|president\s+of|weather\s+in|translate\s+"
    r"|recipe\s+for|solve\s+this\s+(math|equation)|who\s+won|sports?\s+score)",
    re.IGNORECASE,
)

_ANALYTICAL_PATTERN = re.compile(
    r"(analy[sz]|breakdown|compare|trend|segment|performance|overview|executive\s+summary"
    r"|insight|diagnos|assess|evaluat|health\s*check|benchmark|year.over.year|month.over.month"
    r"|identify.*opportunit|deep\s*dive)",
    re.IGNORECASE,
)

# ── Direct query routing (Phase 1.4) — skip LLM for simple factual queries ──
_DIRECT_ROUTES: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"(revenue\s+by\s+category.*(%|percent|percentage|share))|"
            r"((%|percent|percentage|share).*(revenue\s+by\s+category))",
            re.IGNORECASE,
        ),
        "revenue_share_by_category",
    ),
    (re.compile(r"total\s+revenue", re.IGNORECASE), "total_revenue"),
    (re.compile(r"revenue\s+by\s+month", re.IGNORECASE), "revenue_by_month"),
    (re.compile(r"revenue\s+by\s+category", re.IGNORECASE), "revenue_by_category"),
    (re.compile(r"low\s+stock", re.IGNORECASE), "low_stock"),
    (re.compile(r"out\s+of\s+stock", re.IGNORECASE), "out_of_stock"),
    (re.compile(r"top\s+products?(\s+by\s+revenue)?", re.IGNORECASE), "top_products_by_revenue"),
    (re.compile(r"top\s+products?\s+by\s+quantity", re.IGNORECASE), "top_products_by_quantity"),
    (re.compile(r"top\s+rated\s+products?", re.IGNORECASE), "top_rated_products"),
    (re.compile(r"recent\s+orders?", re.IGNORECASE), "recent_orders"),
    (re.compile(r"pending\s+orders?", re.IGNORECASE), "pending_orders"),
    (re.compile(r"orders?\s+by\s+status", re.IGNORECASE), "orders_by_status"),
    (re.compile(r"orders?\s+today", re.IGNORECASE), "orders_today"),
    (re.compile(r"top\s+customers?", re.IGNORECASE), "top_customers_by_spend"),
    (re.compile(r"customer\s+count|how\s+many\s+customers?", re.IGNORECASE), "customer_count"),
    (re.compile(r"inventory\s+overview", re.IGNORECASE), "inventory_overview"),
    (re.compile(r"rating\s+distribution", re.IGNORECASE), "rating_distribution"),
    (re.compile(r"stockout\s+risk", re.IGNORECASE), "stockout_risk"),
    (re.compile(r"worst\s+rated", re.IGNORECASE), "worst_rated_products"),
    (re.compile(r"new\s+customers?\s+this\s+month", re.IGNORECASE), "new_customers_this_month"),
    (re.compile(r"sales?\s+last\s+30\s*d", re.IGNORECASE), "sales_last_30d"),
    (re.compile(r"sales?\s+last\s+7\s*d", re.IGNORECASE), "sales_last_7d"),
    (re.compile(r"customer\s+segments?", re.IGNORECASE), "customer_segments"),
    (re.compile(r"api\s+usage", re.IGNORECASE), "api_usage_summary"),
]


@dataclass(frozen=True)
class ResponseMode:
    name: str
    max_tokens: int
    max_tool_calls: int
    mode_instruction: str


# ── Mode definitions ─────────────────────────────────────────────────────────

MODES = {
    "greeting": ResponseMode(
        name="greeting",
        max_tokens=0,
        max_tool_calls=0,
        mode_instruction="[MODE: GREETING]",
    ),
    "off_topic": ResponseMode(
        name="off_topic",
        max_tokens=0,
        max_tool_calls=0,
        mode_instruction="[MODE: OFF_TOPIC]",
    ),
    "factual": ResponseMode(
        name="factual",
        max_tokens=600,
        max_tool_calls=2,
        mode_instruction=(
            "[MODE: FACTUAL] Max 200 words. Summary + table + 1-sentence takeaway. "
            "No recommended actions unless data is surprising. No filler. "
            "ALWAYS call all needed tools in a SINGLE response — never one at a time."
        ),
    ),
    "analytical": ResponseMode(
        name="analytical",
        max_tokens=1000,
        max_tool_calls=2,
        mode_instruction=(
            "[MODE: ANALYTICAL] Max 400 words. CRITICAL: In your FIRST response, call all needed "
            "tools simultaneously (e.g., query_library + sql_query in parallel). Do NOT call "
            "tools one at a time. Summary + breakdown table + key takeaway "
            "+ 2-3 recommended actions. Every recommendation must cite a specific product "
            "or dollar amount."
        ),
    ),
    "chart": ResponseMode(
        name="chart",
        max_tokens=800,
        max_tool_calls=3,
        mode_instruction=(
            "[MODE: CHART] You MUST use python_executor to generate a chart. "
            "NEVER respond with only a table. NEVER output raw Python code. "
            "Max 150 words of text (excluding chart). Context line + chart "
            "+ exactly 1 INSIGHT line + exactly 1 ACTION line. No other commentary. "
            "Call data query + python_executor together when possible. "
            "IMPORTANT: Reserve at least 1 tool call for python_executor — "
            "do NOT spend all tool calls on data queries."
        ),
    ),
    "hitl": ResponseMode(
        name="hitl",
        max_tokens=2000,
        max_tool_calls=2,
        mode_instruction=(
            "[MODE: HITL] CRITICAL: In your FIRST response, call exactly 2 tools simultaneously "
            "(e.g., query_library + rag_search). Do NOT call tools one at a time across multiple "
            "turns. Then IMMEDIATELY output the HITL_REQUEST JSON block. "
            "Do NOT write preamble text before the JSON. "
            "Go straight to the ```json HITL_REQUEST block. No charts before approval. "
            "Keep artifacts_preview compact — use tables, not paragraphs."
        ),
    ),
    "rag": ResponseMode(
        name="rag",
        max_tokens=600,
        max_tool_calls=2,
        mode_instruction=(
            "[MODE: RAG] Max 200 words. Direct answer + policy excerpt + source. "
            "No elaboration beyond what the document says."
        ),
    ),
    "web": ResponseMode(
        name="web",
        max_tokens=800,
        max_tool_calls=1,
        mode_instruction=(
            "[MODE: WEB] Use ONLY web_search. Do NOT query the internal database. "
            "Summarize findings with sources. Max 300 words."
        ),
    ),
    "prospecting": ResponseMode(
        name="prospecting",
        max_tokens=1200,
        max_tool_calls=2,
        mode_instruction=(
            "[MODE: PROSPECTING] Max 500 words. Lead with the business pain, not the technology. "
            "Every paragraph must contain a number or specific product/workflow reference. "
            "Run at least one live query as proof. End with a question for the prospect. "
            "Output must fit on one slide — use tables and bullets, not paragraphs. "
            "ALWAYS call all needed tools in a SINGLE response."
        ),
    ),
}


def match_direct_query(message: str) -> str | None:
    """Try to match a user message to a direct query_library entry.

    Returns the query_name if matched, None otherwise.
    Only matches simple, short messages (< 80 chars, no complex connectors).
    """
    stripped = message.strip()
    # Only route short, simple questions — complex ones need LLM reasoning
    if len(stripped) > 80:
        return None
    # Skip if the message contains complex connectors suggesting multi-step reasoning
    if re.search(r"\b(and|but|then|also|compare|versus|vs)\b", stripped, re.IGNORECASE):
        return None
    # Skip direct-query routing when the user is clearly asking for another workflow.
    if _HITL_PATTERN.search(stripped) or _CHART_PATTERN.search(stripped) or _OFF_TOPIC_PATTERN.search(stripped):
        return None
    if _RAG_PATTERN.search(stripped):
        return None
    if _WEB_PATTERN.search(stripped):
        return None
    # Skip direct routing when a category/filter qualifier is present
    # e.g. "total revenue from Electronics" needs a filtered query, not total_revenue
    if re.search(r"\b(from|for|in|of)\s+[A-Z]", stripped):
        return None

    for pattern, query_name in _DIRECT_ROUTES:
        if pattern.search(stripped):
            return query_name
    return None


def classify_mode(message: str) -> ResponseMode:
    """Classify a user message into a response mode.

    Uses keyword/heuristic matching. Order matters — more specific modes
    are checked first (HITL > chart > prospecting > RAG > analytical > factual).
    """
    # Greetings / trivial messages — fast lane, no LLM call
    stripped = message.strip()
    if _GREETING_PATTERN.match(stripped):
        return MODES["greeting"]

    # Obvious non-commerce prompts should not spend tool budget.
    if _OFF_TOPIC_PATTERN.search(message):
        return MODES["off_topic"]

    # HITL triggers take priority — they have the most complex workflow
    if _HITL_PATTERN.search(message):
        return MODES["hitl"]

    # Chart requests
    if _CHART_PATTERN.search(message):
        return MODES["chart"]

    # Web / external research
    if _WEB_PATTERN.search(message):
        return MODES["web"]

    # Prospecting / discovery
    if _PROSPECTING_PATTERN.search(message):
        return MODES["prospecting"]

    # Hybrid prompts that need both data analysis and policy context should stay in
    # analytical mode so the model can produce separate data + policy sections.
    if _RAG_PATTERN.search(message) and (_ANALYTICAL_PATTERN.search(message) or _DATA_REQUEST_PATTERN.search(message)):
        return MODES["analytical"]

    # RAG / policy questions
    if _RAG_PATTERN.search(message):
        return MODES["rag"]

    # Analytical / multi-dimensional questions
    if _ANALYTICAL_PATTERN.search(message):
        return MODES["analytical"]

    # Default: factual
    return MODES["factual"]

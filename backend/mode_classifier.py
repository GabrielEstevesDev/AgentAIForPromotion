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
    r"(strateg|promoti|campaign|refund|dispute|complaint|email\s+(to|for|draft)"
    r"|purchase\s*order|replenish|restock|reorder|create\s+a?\s*PO\b)",
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
    r"|internal\s+doc|guideline|procedure|support\s+guide)",
    re.IGNORECASE,
)

_ANALYTICAL_PATTERN = re.compile(
    r"(analy[sz]|breakdown|compare|trend|segment|performance|overview|executive\s+summary"
    r"|insight|diagnos|assess|evaluat|health\s*check|benchmark|year.over.year|month.over.month"
    r"|identify.*opportunit|deep\s*dive)",
    re.IGNORECASE,
)


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
    "factual": ResponseMode(
        name="factual",
        max_tokens=600,
        max_tool_calls=3,
        mode_instruction=(
            "[MODE: FACTUAL] Max 200 words. Summary + table + 1-sentence takeaway. "
            "No recommended actions unless data is surprising. No filler."
        ),
    ),
    "analytical": ResponseMode(
        name="analytical",
        max_tokens=1000,
        max_tool_calls=3,
        mode_instruction=(
            "[MODE: ANALYTICAL] Max 400 words. Call multiple tools in parallel when data needs "
            "are independent. Summary + breakdown table + key takeaway "
            "+ 2-3 recommended actions. Every recommendation must cite a specific product "
            "or dollar amount."
        ),
    ),
    "chart": ResponseMode(
        name="chart",
        max_tokens=800,
        max_tool_calls=4,
        mode_instruction=(
            "[MODE: CHART] Max 150 words of text (excluding chart). Context line + chart "
            "+ exactly 1 INSIGHT line + exactly 1 ACTION line. No other commentary."
        ),
    ),
    "hitl": ResponseMode(
        name="hitl",
        max_tokens=2000,
        max_tool_calls=5,
        mode_instruction=(
            "[MODE: HITL] CRITICAL: Use at most 2 tool calls for data — call both in parallel. "
            "Then IMMEDIATELY output the HITL_REQUEST JSON block. "
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
    "prospecting": ResponseMode(
        name="prospecting",
        max_tokens=1200,
        max_tool_calls=3,
        mode_instruction=(
            "[MODE: PROSPECTING] Max 500 words. Lead with the business pain, not the technology. "
            "Every paragraph must contain a number or specific product/workflow reference. "
            "Run at least one live query as proof. End with a question for the prospect. "
            "Output must fit on one slide — use tables and bullets, not paragraphs."
        ),
    ),
}


def classify_mode(message: str) -> ResponseMode:
    """Classify a user message into a response mode.

    Uses keyword/heuristic matching. Order matters — more specific modes
    are checked first (HITL > chart > prospecting > RAG > analytical > factual).
    """
    # Greetings / trivial messages — fast lane, no LLM call
    stripped = message.strip()
    if _GREETING_PATTERN.match(stripped):
        return MODES["greeting"]

    # HITL triggers take priority — they have the most complex workflow
    if _HITL_PATTERN.search(message):
        return MODES["hitl"]

    # Chart requests
    if _CHART_PATTERN.search(message):
        return MODES["chart"]

    # Prospecting / discovery
    if _PROSPECTING_PATTERN.search(message):
        return MODES["prospecting"]

    # RAG / policy questions
    if _RAG_PATTERN.search(message):
        return MODES["rag"]

    # Analytical / multi-dimensional questions
    if _ANALYTICAL_PATTERN.search(message):
        return MODES["analytical"]

    # Default: factual
    return MODES["factual"]

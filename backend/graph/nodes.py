"""Node functions and Runnable chains for the Aria StateGraph."""

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
from ..validators import check_summary_breakdown_coherence, validate_hitl_structure

logger = logging.getLogger(__name__)

# Keywords that indicate PO/replenishment intent
_PO_KEYWORDS = re.compile(
    r"(purchase\s*order|replenish|restock|reorder|low\s*stock|supplier|PO\b)",
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

    # Classify mode
    t0 = time.perf_counter()
    mode = classify_mode(user_text)
    classify_dur = time.perf_counter() - t0
    logger.info("PERF_LOG: [Mode Classification] - %.4fs", classify_dur)

    if direct_query_name:
        logger.info("Mode: direct_query -> %s (skipping LLM)", direct_query_name)
    else:
        logger.info("Mode: %s (max_tools=%d)", mode.name, mode.max_tool_calls)

    # Detect HITL approval
    msg_lower = user_text.lower()
    is_hitl_approval = "[hitl response]" in msg_lower and "approve" in msg_lower

    # Detect PO intent (sticky — once set, stays True)
    po_intent = state.get("po_intent", False)
    if _PO_KEYWORDS.search(user_text):
        po_intent = True

    # Prepend mode instruction to the user message
    augmented_content = f"{mode.mode_instruction}\n\n{user_text}"
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
    "hello": "Hello! I'm Aria, your e-commerce assistant. How can I help you today?",
    "hi": "Hello! I'm Aria, your e-commerce assistant. How can I help you today?",
    "hey": "Hey! I'm Aria, your e-commerce assistant. How can I help you today?",
    "thanks": "You're welcome! Let me know if you need anything else.",
    "thank you": "You're welcome! Let me know if you need anything else.",
    "ok": "Got it! Let me know if you need anything else.",
    "okay": "Got it! Let me know if you need anything else.",
    "got it": "Got it! Let me know if you need anything else.",
    "sure": "Sure thing! What would you like to do next?",
    "who are you": "I'm Aria, an AI-powered e-commerce assistant. I can analyze sales data, search our knowledge base, create charts, and manage purchase orders with approval workflows.",
    "what can you do": "I'm Aria, an AI-powered e-commerce assistant. I can analyze sales data, search our knowledge base, create charts, and manage purchase orders with approval workflows.",
    "what are you": "I'm Aria, an AI-powered e-commerce assistant. I can analyze sales data, search our knowledge base, create charts, and manage purchase orders with approval workflows.",
}
_GREETING_DEFAULT = "Hello! I'm Aria, your e-commerce assistant. How can I help you today?"


def fast_response(state: dict) -> dict:
    """Return a hardcoded response for greetings. No LLM call."""
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

    response_text = f"### {query_name.replace('_', ' ').title()}\n\n{result}"
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
    msgs.append(SystemMessage(content=_STOP_TOOLS_MSG))
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

    # Look for ```json blocks containing HITL_REQUEST
    json_blocks = re.findall(r"```json\s*\n(.*?)```", content, re.DOTALL)
    for block in json_blocks:
        try:
            parsed = json.loads(block.strip())
            if "HITL_REQUEST" in parsed:
                logger.info("HITL_REQUEST detected in AI response")
                return {"needs_hitl": True, "hitl_payload": parsed["HITL_REQUEST"]}
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

    logger.info("Graph resumed with decision: %s", decision.get("action", "unknown"))
    return {"hitl_decision": decision, "hitl_approved": True}


# ---------------------------------------------------------------------------
# Node: post_approve (Runnable chain for streaming)
# ---------------------------------------------------------------------------

def _approve_preprocess(state: dict) -> list:
    """Build messages for post-approval LLM call."""
    decision = state.get("hitl_decision", {})
    action = decision.get("action", "approve")
    controls = decision.get("controls", {})
    notes = decision.get("notes", "")

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

    coherence_note = check_summary_breakdown_coherence(response_text)
    if coherence_note:
        response_text += coherence_note
        logger.info("Appended coherence note to response")

    hitl_warnings = validate_hitl_structure(response_text)
    if hitl_warnings:
        logger.warning("HITL validation warnings: %s", hitl_warnings)

    return {"response_text": response_text}

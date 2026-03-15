import asyncio
import logging
import os
import re
from typing import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from .config import LLM_MODEL, OPENAI_API_KEY
from .core.system_prompt import SYSTEM_PROMPT
from .hitl_state import set_approval, set_po_intent
from .mode_classifier import classify_mode
from .tools import ALL_TOOLS

os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

logger = logging.getLogger(__name__)

# Keywords that indicate the user actually wants PO/replenishment functionality
_PO_KEYWORDS = re.compile(
    r"(purchase\s*order|replenish|restock|reorder|low\s*stock|supplier|PO\b)",
    re.IGNORECASE,
)

# Maximum time (seconds) for the full agent run before aborting
_AGENT_TIMEOUT_SEC = 90

# Heartbeat interval (seconds) — keep SSE alive during long tool executions
_HEARTBEAT_INTERVAL_SEC = 5

# Default maximum number of tool calls before forcing the agent to respond
_DEFAULT_MAX_TOOL_CALLS = 5

# Message injected after max tool calls to force the agent to stop and answer
_STOP_TOOLS_MSG = (
    "STOP. DO NOT CALL ANY MORE TOOLS. You have reached your tool call limit. "
    "You MUST immediately produce your final text response using ONLY the data "
    "you have already gathered. If the user's request requires a HITL_REQUEST "
    "(email, strategy, purchase order), output the HITL_REQUEST JSON block now. "
    "Otherwise, write your analysis and answer. ANY further tool call will be "
    "blocked. Respond with TEXT ONLY. Keep your response concise."
)


def build_agent():
    """Build the single ReAct agent used for all requests."""
    llm = ChatOpenAI(
        model=LLM_MODEL,
        temperature=0,
        timeout=60,
        max_tokens=3500,
    )
    memory = MemorySaver()
    return create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        checkpointer=memory,
        prompt=SYSTEM_PROMPT,
    )


async def stream_agent(agent, message: str, thread_id: str) -> AsyncIterator[str]:
    # Classify response mode BEFORE running the agent
    mode = classify_mode(message)
    max_tool_calls = mode.max_tool_calls
    logger.info(
        "Mode: %s (max_tools=%d) [thread=%s]",
        mode.name, max_tool_calls, thread_id,
    )

    # Mark thread as HITL-approved when the user message is an approval response
    msg_lower = message.lower()
    is_hitl_approval = "[hitl response]" in msg_lower and "approve" in msg_lower
    set_approval(thread_id, is_hitl_approval)

    # Track whether the user has ever explicitly asked for PO/replenishment in this thread
    if _PO_KEYWORDS.search(message):
        set_po_intent(thread_id, True)

    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 15}

    # Prepend mode instruction to the user message so the LLM sees it
    augmented_message = f"{mode.mode_instruction}\n\n{message}"

    # SQL queries captured from tool calls — injected before the first response token
    pending_sqls: list[str] = []
    sql_injected = False

    # Use an async queue so we can inject heartbeats between real tokens
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    agent_error: list[Exception] = []

    async def _patch_orphaned_tool_calls():
        """Fix corrupted checkpoint: add ToolMessages for AIMessages with dangling tool_calls."""
        try:
            state = agent.get_state(config)
            messages = state.values.get("messages", [])
            if not messages:
                return
            last_msg = messages[-1]
            tool_calls = getattr(last_msg, "tool_calls", None)
            if not tool_calls:
                return
            for tc in tool_calls:
                agent.update_state(
                    config,
                    {"messages": [ToolMessage(
                        content="[Tool call limit reached. Use the data already gathered to respond.]",
                        tool_call_id=tc["id"],
                    )]},
                )
            logger.info(
                "Patched %d orphaned tool call(s) for thread %s",
                len(tool_calls), thread_id,
            )
        except Exception as exc:
            logger.warning("Failed to patch orphaned tool calls: %s", exc)

    async def _run_with_retry():
        """Run the agent, and if it exhausts tool calls without producing text,
        re-invoke with a forced-stop system message."""
        tool_call_count = 0
        produced_text = False

        # Fix any pre-existing corrupted state from a previous broken run
        await _patch_orphaned_tool_calls()

        try:
            async for event in agent.astream_events(
                {"messages": [HumanMessage(content=augmented_message)]},
                config=config,
                version="v2",
            ):
                event_type = event.get("event")

                # --- Log & count tool calls ---
                if event_type == "on_tool_start":
                    tool_call_count += 1
                    tool_name = event.get("name", "unknown")
                    tool_input = str(event.get("data", {}).get("input", ""))[:100]
                    logger.info(
                        "Tool call #%d/%d: %s(%s) [thread=%s]",
                        tool_call_count, max_tool_calls, tool_name, tool_input, thread_id,
                    )
                    continue

                if event_type == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    output_preview = str(event.get("data", {}).get("output", ""))[:120]
                    logger.info("Tool done: %s -> %s", tool_name, output_preview)

                    # Capture SQL from sql_query tool calls
                    if tool_name == "sql_query":
                        tool_input = event.get("data", {}).get("input", {})
                        sql = ""
                        if isinstance(tool_input, dict):
                            sql = tool_input.get("query", "").strip()
                        elif isinstance(tool_input, str):
                            sql = tool_input.strip()
                        if sql:
                            pending_sqls.append(sql)

                    if tool_call_count >= max_tool_calls:
                        logger.warning(
                            "Tool call limit (%d) reached for thread %s — breaking to force response",
                            max_tool_calls, thread_id,
                        )
                        break  # Exit astream_events loop
                    continue

                if event_type != "on_chat_model_stream":
                    continue

                chunk = event.get("data", {}).get("chunk")

                # Skip tool-call chunks (intermediate ReAct steps)
                tool_call_chunks = getattr(chunk, "tool_call_chunks", None)
                if tool_call_chunks:
                    continue

                token = getattr(chunk, "content", None)
                text = _extract_text(token)
                if not text:
                    continue

                produced_text = True
                await queue.put(text)

        except Exception as exc:
            # If we hit recursion limit and never produced text, do a forced follow-up
            exc_msg = str(exc).lower()
            if not produced_text and ("recursion" in exc_msg or tool_call_count >= max_tool_calls):
                logger.warning(
                    "Agent hit limit (%d tools, error=%s) without text — forcing final response",
                    tool_call_count, type(exc).__name__,
                )
                await _patch_orphaned_tool_calls()
                await _force_final_response()
                return
            logger.exception("Agent error for thread %s", thread_id)
            agent_error.append(exc)
            return

        # If the agent finished but never produced text (all tool calls, no answer),
        # force a follow-up — patch state first in case break left orphaned tool_calls
        if not produced_text and tool_call_count > 0:
            logger.warning(
                "Agent made %d tool calls but produced no text — forcing final response [thread=%s]",
                tool_call_count, thread_id,
            )
            await _patch_orphaned_tool_calls()
            await _force_final_response()

    async def _force_final_response():
        """Send a follow-up message forcing the agent to produce text with the data it has."""
        produced_any = False
        try:
            force_config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 3}
            async for event in agent.astream_events(
                {"messages": [HumanMessage(content=_STOP_TOOLS_MSG)]},
                config=force_config,
                version="v2",
            ):
                event_type = event.get("event")
                if event_type != "on_chat_model_stream":
                    continue

                chunk = event.get("data", {}).get("chunk")
                tool_call_chunks = getattr(chunk, "tool_call_chunks", None)
                if tool_call_chunks:
                    continue

                token = getattr(chunk, "content", None)
                text = _extract_text(token)
                if not text:
                    continue

                produced_any = True
                await queue.put(text)
        except Exception as exc:
            logger.exception("Forced response also failed for thread %s", thread_id)
            await _patch_orphaned_tool_calls()
            if not produced_any:
                agent_error.append(exc)

        # Last resort: if forced response also produced nothing, emit a fallback
        if not produced_any and not agent_error:
            fallback = (
                "I gathered the data but couldn't assemble a full response. "
                "Please try rephrasing your question or breaking it into smaller steps."
            )
            await queue.put(fallback)

    # Launch the agent as a background task
    async def _wrapped():
        try:
            await _run_with_retry()
        finally:
            await queue.put(None)  # sentinel: agent is done

    agent_task = asyncio.create_task(_wrapped())

    try:
        deadline = asyncio.get_event_loop().time() + _AGENT_TIMEOUT_SEC

        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                agent_task.cancel()
                # Patch state so the thread isn't permanently broken after timeout
                try:
                    await _patch_orphaned_tool_calls()
                except Exception:
                    pass
                yield "\n\n⚠️ The request took too long and was stopped. Please try a simpler question or break it into smaller steps."
                return

            try:
                token = await asyncio.wait_for(
                    queue.get(), timeout=min(_HEARTBEAT_INTERVAL_SEC, remaining)
                )
            except asyncio.TimeoutError:
                # No token received — send a heartbeat comment to keep SSE alive
                yield ""
                continue

            if token is None:
                # Agent finished
                break

            # Before the first real text token, inject captured SQL blocks
            if pending_sqls and not sql_injected:
                sql_injected = True
                for sql in pending_sqls:
                    yield f"```sql\n{sql}\n```\n\n"

            yield token

        # If the agent errored, raise so the caller can send an SSE error event
        if agent_error:
            raise agent_error[0]

    finally:
        if not agent_task.done():
            agent_task.cancel()
            try:
                await agent_task
            except (asyncio.CancelledError, Exception):
                pass


def _extract_text(token) -> str:
    if isinstance(token, str):
        return token
    if isinstance(token, list):
        parts = []
        for item in token:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(text)
        return "".join(parts)
    return ""

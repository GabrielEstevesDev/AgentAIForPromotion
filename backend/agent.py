import asyncio
import logging
import os
import re
from typing import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from .config import LLM_MODEL, OPENAI_API_KEY
from .core.system_prompt import SYSTEM_PROMPT
from .hitl_state import set_approval, set_po_intent
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
_HEARTBEAT_INTERVAL_SEC = 8

# Maximum number of tool calls before forcing the agent to respond
_MAX_TOOL_CALLS = 10

# Message injected after max tool calls to force the agent to stop and answer
_STOP_TOOLS_MSG = (
    "IMPORTANT: You have already used many tools. You MUST now produce your final "
    "answer using the data you have gathered so far. Do NOT call any more tools. "
    "Respond directly to the user with your analysis, including any HITL_REQUEST "
    "if required."
)


def build_agent():
    llm = ChatOpenAI(model=LLM_MODEL, temperature=0, timeout=60)
    memory = MemorySaver()
    return create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        checkpointer=memory,
        prompt=SYSTEM_PROMPT,
    )


async def stream_agent(agent, message: str, thread_id: str) -> AsyncIterator[str]:
    # Mark thread as HITL-approved when the user message is an approval response
    msg_lower = message.lower()
    is_hitl_approval = "[hitl response]" in msg_lower and "approve" in msg_lower
    set_approval(thread_id, is_hitl_approval)

    # Track whether the user has ever explicitly asked for PO/replenishment in this thread
    if _PO_KEYWORDS.search(message):
        set_po_intent(thread_id, True)

    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 25}

    # SQL queries captured from tool calls — injected before the first response token
    pending_sqls: list[str] = []
    sql_injected = False

    # Use an async queue so we can inject heartbeats between real tokens
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    agent_error: list[Exception] = []

    async def _run_agent():
        """Run the agent loop and push tokens/sentinels into the queue."""
        tool_call_count = 0
        forced_stop = False

        try:
            async for event in agent.astream_events(
                {"messages": [HumanMessage(content=message)]},
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
                        "Tool call #%d: %s(%s) [thread=%s]",
                        tool_call_count, tool_name, tool_input, thread_id,
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

                    # If we've hit the tool call limit, force the agent to stop
                    if tool_call_count >= _MAX_TOOL_CALLS and not forced_stop:
                        forced_stop = True
                        logger.warning(
                            "Tool call limit (%d) reached for thread %s — forcing response",
                            _MAX_TOOL_CALLS, thread_id,
                        )
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

                await queue.put(text)

        except Exception as exc:
            logger.exception("Agent error for thread %s", thread_id)
            agent_error.append(exc)
        finally:
            await queue.put(None)  # sentinel: agent is done

    async def _run_with_retry():
        """Run the agent, and if it exhausts tool calls without producing text,
        re-invoke with a forced-stop system message."""
        tool_call_count = 0
        produced_text = False

        try:
            async for event in agent.astream_events(
                {"messages": [HumanMessage(content=message)]},
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
                        "Tool call #%d: %s(%s) [thread=%s]",
                        tool_call_count, tool_name, tool_input, thread_id,
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
            if not produced_text and ("recursion" in exc_msg or tool_call_count >= _MAX_TOOL_CALLS):
                logger.warning(
                    "Agent hit limit (%d tools, error=%s) without text — forcing final response",
                    tool_call_count, type(exc).__name__,
                )
                await _force_final_response()
                return
            logger.exception("Agent error for thread %s", thread_id)
            agent_error.append(exc)
            return

        # If the agent finished but never produced text (all tool calls, no answer),
        # force a follow-up
        if not produced_text and tool_call_count > 0:
            logger.warning(
                "Agent made %d tool calls but produced no text — forcing final response [thread=%s]",
                tool_call_count, thread_id,
            )
            await _force_final_response()

    async def _force_final_response():
        """Send a follow-up message forcing the agent to produce text with the data it has."""
        try:
            force_config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 4}
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

                await queue.put(text)
        except Exception as exc:
            logger.exception("Forced response also failed for thread %s", thread_id)
            agent_error.append(exc)

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

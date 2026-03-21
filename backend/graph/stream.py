"""Streaming function for the AgenticStack StateGraph.

Replaces the 300-line stream_agent() in the old agent.py. Responsibilities:
- astream_events() consumer that yields text tokens from on_chat_model_stream
- Heartbeat wrapper (5s empty token for SSE keep-alive)
- 90s overall timeout
- No tool counting (graph handles it), no orphan patching, no forced response injection
- Trace event collection for the Trace Inspector feature
"""

import asyncio
import json
import logging
import re
import time
from typing import AsyncIterator

from langchain_core.messages import HumanMessage
from langgraph.errors import GraphInterrupt
from langgraph.types import Command

logger = logging.getLogger(__name__)

# Prefix for trace data pushed through the queue (similar to PERF_PREFIX)
TRACE_PREFIX = "\x00TRACE:"

# Status messages emitted on tool start for perceived latency reduction
_TOOL_STATUS = {
    "sql_query": "\n\n\U0001f50d Querying database...\n\n",
    "query_library": "\n\n\U0001f4ca Looking up data...\n\n",
    "rag_search": "\n\n\U0001f4da Searching knowledge base...\n\n",
    "web_search": "\n\n\U0001f310 Searching the web...\n\n",
    "python_executor": "\n\n\U0001f40d Running analysis...\n\n",
    "purchase_order_action": "\n\n\U0001f4e6 Processing order...\n\n",
}

# Maximum time (seconds) for the full agent run before aborting
_AGENT_TIMEOUT_SEC = 90

# Heartbeat interval (seconds) — keep SSE alive during long tool executions
_HEARTBEAT_INTERVAL_SEC = 5

# Per-thread locks to prevent concurrent requests from corrupting checkpoints
_thread_locks: dict[str, asyncio.Lock] = {}


def _get_thread_lock(thread_id: str) -> asyncio.Lock:
    """Get or create a per-thread asyncio lock."""
    if thread_id not in _thread_locks:
        _thread_locks[thread_id] = asyncio.Lock()
    return _thread_locks[thread_id]


def cleanup_thread_locks(thread_ids: list[str]) -> int:
    """Remove stale entries from _thread_locks for deleted threads.

    Only removes locks that are not currently held.
    Returns the number of locks removed.
    """
    removed = 0
    for tid in thread_ids:
        lock = _thread_locks.get(tid)
        if lock is not None and not lock.locked():
            del _thread_locks[tid]
            removed += 1
    return removed


def _extract_text(token) -> str:
    """Extract text content from various token formats."""
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


def _parse_hitl_response(content: str) -> dict:
    """Parse a [HITL Response] message into a decision dict for Command(resume=...).

    Expected format:
        [HITL Response] hitlId:<id>
        Action: <action>
        Controls: <json>
        Notes: <text>
    """
    # Extract Action line
    action = "approve"
    action_match = re.search(r"^Action:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE)
    if action_match:
        action = action_match.group(1).strip()

    # Extract Controls JSON
    controls = {}
    controls_match = re.search(r"^Controls:\s*(\{.*\})", content, re.MULTILINE | re.DOTALL)
    if controls_match:
        try:
            controls = json.loads(controls_match.group(1))
        except json.JSONDecodeError:
            pass

    # Extract Notes
    notes = ""
    notes_match = re.search(r"^Notes:\s*(.+)$", content, re.MULTILINE | re.DOTALL)
    if notes_match:
        notes = notes_match.group(1).strip()

    return {"action": action, "controls": controls, "notes": notes}


async def stream_graph(graph, message: str, thread_id: str) -> AsyncIterator[str]:
    """Stream tokens from the AgenticStack StateGraph.

    Args:
        graph: Compiled StateGraph instance.
        message: User's message text.
        thread_id: Conversation thread ID (maps to checkpointer thread).

    Yields:
        Text tokens for SSE streaming. Empty strings are heartbeats.
    """
    lock = _get_thread_lock(thread_id)
    async with lock:
        async for token in _stream_graph_inner(graph, message, thread_id):
            yield token


async def _stream_graph_inner(graph, message: str, thread_id: str) -> AsyncIterator[str]:
    """Inner streaming implementation (called under per-thread lock)."""
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 25}

    # ── Trace event collection ──
    trace_events: list[dict] = []
    trace_start = time.perf_counter()

    def _trace(event_type: str, **data):
        """Append a trace event with a relative timestamp."""
        trace_events.append({
            "type": event_type,
            "ts": round(time.perf_counter() - trace_start, 4),
            **data,
        })

    # Determine if this is a HITL resume or a new message
    is_hitl_resume = "[hitl response]" in message.lower()

    if is_hitl_resume:
        decision = _parse_hitl_response(message)
        input_value = Command(resume=decision)
        logger.info("Resuming graph with HITL decision: %s [thread=%s]", decision.get("action"), thread_id)
        _trace("hitl_resume", action=decision.get("action", "unknown"))
    else:
        input_value = {"messages": [HumanMessage(content=message)]}
        _trace("user_message", length=len(message))

    # Phase 1.1: Immediate status message for perceived <500ms TTFT
    if not is_hitl_resume:
        yield "\u2728 Analyzing your request...\n\n"

    # SQL queries captured from tool calls — injected before the first response token
    pending_sqls: list[str] = []
    sql_injected = False

    # Use an async queue so we can inject heartbeats between real tokens
    # Special perf markers use prefix \x00PERF: to distinguish from real text
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    agent_error: list[Exception] = []

    # Prefix for perf markers pushed through the queue
    PERF_PREFIX = "\x00PERF:"

    async def _emit_perf(name: str, duration: float, **extra):
        """Push a perf marker into the queue for SSE emission."""
        payload = {"name": name, "duration": round(duration, 4), **extra}
        await queue.put(PERF_PREFIX + json.dumps(payload))

    async def _run():
        """Run the graph and push tokens to the queue."""
        nonlocal sql_injected

        # ── PERF tracking state ──
        perf_graph_start = time.perf_counter()
        perf_first_llm_chunk: float = 0.0       # first on_chat_model_stream event
        perf_first_tool_start: float = 0.0       # first on_tool_start event
        perf_first_text_token: float = 0.0       # first visible text token (not tool-call chunk)
        perf_llm_call_count = 0                  # how many LLM invocations we've seen
        perf_tool_times: list[tuple[str, float, float]] = []  # (name, start, end)
        perf_active_tools: dict[str, float] = {} # run_id -> start time
        perf_llm_call_starts: dict[str, float] = {}  # run_id -> start time for each LLM call
        any_text_emitted = False

        # Track active node runs for duration calculation
        perf_node_starts: dict[str, float] = {}
        # Known graph node names (to filter out internal chains)
        _GRAPH_NODES = {
            "summarize_if_needed", "classify", "fast_response", "direct_query",
            "direct_chart", "plan_and_call", "execute_tools", "force_respond",
            "extract_hitl", "hitl_gate", "inject_revision_request", "post_approve",
            "assemble_response", "validate",
        }

        try:
            async for event in graph.astream_events(
                input_value,
                config=config,
                version="v2",
            ):
                event_type = event.get("event")

                # ── Trace: capture graph node entry/exit ──
                if event_type == "on_chain_start":
                    chain_name = event.get("name", "")
                    if chain_name in _GRAPH_NODES:
                        run_id = event.get("run_id", "")
                        perf_node_starts[run_id] = time.perf_counter()
                        _trace("node_start", name=chain_name)
                    continue

                if event_type == "on_chain_end":
                    chain_name = event.get("name", "")
                    run_id = event.get("run_id", "")
                    if chain_name in _GRAPH_NODES and run_id in perf_node_starts:
                        dur = time.perf_counter() - perf_node_starts.pop(run_id)
                        extra = {}
                        # Capture classify output details
                        if chain_name == "classify":
                            output = event.get("data", {}).get("output", {})
                            if isinstance(output, dict):
                                extra["mode"] = output.get("mode", "")
                                extra["direct_query"] = output.get("direct_query_name", "")
                                extra["direct_chart"] = output.get("direct_chart_name", "")
                                extra["po_intent"] = output.get("po_intent", False)
                                max_tools = (output.get("mode_config") or {}).get("max_tool_calls", 0)
                                extra["max_tool_calls"] = max_tools
                        _trace("node_end", name=chain_name, duration=round(dur, 4), **extra)
                    continue

                # ── PERF: Track LLM call start ──
                if event_type == "on_chat_model_start":
                    perf_llm_call_count += 1
                    run_id = event.get("run_id", "")
                    now = time.perf_counter()
                    perf_llm_call_starts[run_id] = now
                    _trace("llm_start", call_number=perf_llm_call_count)
                    if perf_llm_call_count == 1:
                        dur = now - perf_graph_start
                        logger.info("PERF_LOG: [Request Received -> First LLM Call] - %.3fs", dur)
                        await _emit_perf("Request -> First LLM Call", dur)
                    continue

                # ── PERF: Track LLM call end ──
                if event_type == "on_chat_model_end":
                    run_id = event.get("run_id", "")
                    now = time.perf_counter()
                    llm_start = perf_llm_call_starts.pop(run_id, 0.0)
                    if llm_start:
                        llm_dur = now - llm_start
                        logger.info("PERF_LOG: [LLM Call #%d] - %.3fs", perf_llm_call_count, llm_dur)
                        await _emit_perf(f"LLM Call #{perf_llm_call_count}", llm_dur)
                        _trace("llm_end", call_number=perf_llm_call_count, duration=round(llm_dur, 4))
                    continue

                # Log tool activity
                if event_type == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    tool_input = str(event.get("data", {}).get("input", ""))[:100]
                    run_id = event.get("run_id", "")
                    now = time.perf_counter()

                    # Track per-tool timing
                    perf_active_tools[run_id] = now

                    if not perf_first_tool_start:
                        perf_first_tool_start = now
                        # LLM thinking = time from first LLM chunk to first tool call
                        if perf_first_llm_chunk:
                            thinking = perf_first_tool_start - perf_first_llm_chunk
                            logger.info("PERF_LOG: [LLM Thinking Before Tool Call] - %.3fs", thinking)
                            await _emit_perf("LLM Thinking Before Tool Call", thinking)
                        else:
                            elapsed = now - perf_graph_start
                            logger.info("PERF_LOG: [Graph Start -> First Tool Call] - %.3fs", elapsed)
                            await _emit_perf("Graph Start -> First Tool Call", elapsed)

                    logger.info("Tool: %s(%s) [thread=%s]", tool_name, tool_input, thread_id)
                    _trace("tool_start", name=tool_name, input=tool_input)

                    status_text = _TOOL_STATUS.get(tool_name)
                    if status_text:
                        await queue.put(status_text)
                    continue

                if event_type == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    run_id = event.get("run_id", "")
                    now = time.perf_counter()
                    output_preview = str(event.get("data", {}).get("output", ""))[:120]

                    # Track per-tool duration
                    tool_start = perf_active_tools.pop(run_id, 0.0)
                    if tool_start:
                        tool_dur = now - tool_start
                        perf_tool_times.append((tool_name, tool_start, now))
                        logger.info("PERF_LOG: [Tool: %s] - %.3fs", tool_name, tool_dur)
                        await _emit_perf(f"Tool: {tool_name}", tool_dur)
                    logger.info("Tool done: %s -> %s", tool_name, output_preview)
                    if tool_start:
                        _trace("tool_end", name=tool_name, duration=round(tool_dur, 4), output_preview=output_preview)

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

                # Track first LLM stream chunk (includes tool-call chunks)
                if not perf_first_llm_chunk:
                    perf_first_llm_chunk = time.perf_counter()

                chunk = event.get("data", {}).get("chunk")

                # Skip tool-call chunks (intermediate ReAct steps)
                tool_call_chunks = getattr(chunk, "tool_call_chunks", None)
                if tool_call_chunks:
                    continue

                token = getattr(chunk, "content", None)
                text = _extract_text(token)
                if text:
                    # Track first visible text token
                    if not perf_first_text_token:
                        perf_first_text_token = time.perf_counter()
                        ttft = perf_first_text_token - perf_graph_start
                        logger.info("PERF_LOG: [Time to First Text Token (TTFT)] - %.3fs", ttft)
                        await _emit_perf("TTFT (Graph)", ttft)

                    # Before the first real text token, inject captured SQL blocks
                    if pending_sqls and not sql_injected:
                        sql_injected = True
                        for sql in pending_sqls:
                            await queue.put(f"```sql\n{sql}\n```\n\n")

                    await queue.put(text)
                    any_text_emitted = True

        except GraphInterrupt:
            # Expected for HITL — the graph paused at hitl_gate
            logger.info("Graph interrupted (HITL gate) for thread %s", thread_id)
            _trace("hitl_interrupt")
        except Exception as exc:
            logger.exception("Graph error for thread %s", thread_id)
            agent_error.append(exc)
            _trace("error", message=str(exc)[:200])
        finally:
            # Fallback for non-streaming nodes (fast_response path)
            if not any_text_emitted:
                try:
                    snapshot = await graph.aget_state(config)
                    fallback_text = snapshot.values.get("response_text", "")
                    if fallback_text:
                        await queue.put(fallback_text)
                except Exception:
                    pass

            # ── PERF: Summary ──
            total = time.perf_counter() - perf_graph_start
            total_tool = sum(end - start for _, start, end in perf_tool_times)
            llm_time = total - total_tool
            logger.info("PERF_LOG: [Total Tool Execution] - %.3fs (%d call(s))", total_tool, len(perf_tool_times))
            logger.info("PERF_LOG: [Estimated LLM Time] - %.3fs", llm_time)
            logger.info("PERF_LOG: [Total Graph Duration] - %.3fs", total)
            await _emit_perf("Total Tool Execution", total_tool, tool_count=len(perf_tool_times))
            await _emit_perf("Estimated LLM Time", llm_time)
            await _emit_perf("Total Graph Duration", total)

            # ── Emit collected trace events ──
            _trace("graph_end", total_duration=round(total, 4))
            await queue.put(TRACE_PREFIX + json.dumps(trace_events))

    # Launch as background task
    async def _wrapped():
        try:
            await _run()
        finally:
            await queue.put(None)  # sentinel

    agent_task = asyncio.create_task(_wrapped())

    try:
        deadline = asyncio.get_event_loop().time() + _AGENT_TIMEOUT_SEC

        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                agent_task.cancel()
                yield (
                    "\n\n⚠️ The request took too long and was stopped. "
                    "Please try a simpler question or break it into smaller steps."
                )
                return

            try:
                token = await asyncio.wait_for(
                    queue.get(), timeout=min(_HEARTBEAT_INTERVAL_SEC, remaining)
                )
            except asyncio.TimeoutError:
                yield ""  # heartbeat
                continue

            if token is None:
                break

            yield token

        if agent_error:
            raise agent_error[0]

    finally:
        if not agent_task.done():
            agent_task.cancel()
            try:
                await agent_task
            except (asyncio.CancelledError, Exception):
                pass

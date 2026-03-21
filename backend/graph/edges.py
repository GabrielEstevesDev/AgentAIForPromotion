"""Conditional routing edges for the AgenticStack StateGraph."""

import logging

from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)


def route_after_classify(state: dict) -> str:
    """After classify: fast_response for greetings, direct_query for simple lookups, plan_and_call otherwise."""
    if state.get("mode") in {"greeting", "off_topic"}:
        return "fast_response"
    if state.get("mode") == "chart" and state.get("direct_chart_name"):
        return "direct_chart"
    if state.get("mode") == "direct_query" and state.get("direct_query_name"):
        return "direct_query"
    return "plan_and_call"


def route_after_plan(state: dict) -> str:
    """After plan_and_call: route to execute_tools if there are tool calls, else extract_hitl."""
    messages = state.get("messages", [])
    if not messages:
        return "extract_hitl"

    last_msg = messages[-1]
    tool_calls = getattr(last_msg, "tool_calls", None)
    if tool_calls:
        return "execute_tools"

    return "extract_hitl"


def route_after_tools(state: dict) -> str:
    """After execute_tools: loop back to plan_and_call if under limit, else force_respond."""
    tool_count = state.get("tool_call_count", 0)
    mode_config = state.get("mode_config") or {}
    max_tools = mode_config.get("max_tool_calls", 5)

    if tool_count < max_tools:
        logger.info("Tool count %d/%d — looping back to plan_and_call", tool_count, max_tools)
        return "plan_and_call"

    logger.info("Tool count %d/%d — routing to force_respond", tool_count, max_tools)
    return "force_respond"


def route_after_hitl_gate(state: dict) -> str:
    """After hitl_gate: request_changes → inject_revision_request, approve/reject → post_approve."""
    decision = state.get("hitl_decision", {})
    action = decision.get("action", "approve")
    if action == "request_changes":
        logger.info("HITL action is request_changes — routing to inject_revision_request")
        return "inject_revision_request"
    return "post_approve"


def route_after_hitl_check(state: dict) -> str:
    """After extract_hitl: route to hitl_gate if HITL needed, else assemble_response."""
    if state.get("needs_hitl", False):
        return "hitl_gate"
    return "assemble_response"

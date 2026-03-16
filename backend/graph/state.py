"""Graph state schema for the Aria agent."""

import operator
from typing import Annotated, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AriaState(TypedDict):
    """State that flows through the Aria StateGraph.

    Key fields:
    - messages: Chat history managed by LangGraph's add_messages reducer.
    - mode / mode_config: Response mode from the classifier.
    - direct_query_name: If set, skip LLM and run this query_library entry directly.
    - tool_call_count: Incremented by execute_tools; drives the routing edge.
    - captured_sqls: SQL blocks captured from sql_query tool calls (for SQL tab).
    - needs_hitl: Whether the last AI message contains a HITL_REQUEST.
    - hitl_payload: Parsed HITL_REQUEST JSON (set by extract_hitl node).
    - hitl_decision: User's approval/rejection decision (set by interrupt resume).
    - po_intent: Whether the user has expressed PO/replenishment intent.
    - hitl_approved: Whether the current interaction is a HITL approval.
    - summary: Condensed summary of older messages (Phase 3.1).
    - response_text: Final assembled text for persistence (set by assemble_response).
    """

    messages: Annotated[list[BaseMessage], add_messages]
    mode: Optional[str]
    mode_config: Optional[dict]
    direct_query_name: Optional[str]
    tool_call_count: int
    captured_sqls: Annotated[list[str], operator.add]
    needs_hitl: bool
    hitl_payload: Optional[dict]
    hitl_decision: Optional[dict]
    po_intent: bool
    hitl_approved: bool
    summary: Optional[str]
    response_text: str

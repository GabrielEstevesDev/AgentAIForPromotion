"""Build the Aria StateGraph."""

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .edges import route_after_classify, route_after_hitl_check, route_after_plan, route_after_tools
from .nodes import (
    assemble_response,
    classify,
    execute_tools,
    extract_hitl,
    fast_response,
    force_respond,
    hitl_gate,
    plan_and_call,
    post_approve,
    validate,
)
from .state import AriaState

logger = logging.getLogger(__name__)


def build_graph():
    """Build and compile the Aria StateGraph with MemorySaver checkpointer.

    Graph topology:
        START → classify ─┬─ (greeting) → fast_response → END
                          └─ (other)    → plan_and_call
                            ├─ (tool_calls) → execute_tools → route_after_tools
                            │                                   ├─ (under limit) → plan_and_call
                            │                                   └─ (at limit)    → force_respond → extract_hitl
                            └─ (text only)  → extract_hitl
                                              ├─ (needs_hitl)  → hitl_gate → post_approve → assemble_response → validate → END
                                              └─ (no hitl)     → assemble_response → validate → END
    """
    graph = StateGraph(AriaState)

    # Add nodes
    graph.add_node("classify", classify)
    graph.add_node("fast_response", fast_response)
    graph.add_node("plan_and_call", plan_and_call)
    graph.add_node("execute_tools", execute_tools)
    graph.add_node("force_respond", force_respond)
    graph.add_node("extract_hitl", extract_hitl)
    graph.add_node("hitl_gate", hitl_gate)
    graph.add_node("post_approve", post_approve)
    graph.add_node("assemble_response", assemble_response)
    graph.add_node("validate", validate)

    # Edges
    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", route_after_classify, {
        "fast_response": "fast_response",
        "plan_and_call": "plan_and_call",
    })
    graph.add_edge("fast_response", END)

    # After plan_and_call: tool calls → execute, text → extract_hitl
    graph.add_conditional_edges("plan_and_call", route_after_plan, {
        "execute_tools": "execute_tools",
        "extract_hitl": "extract_hitl",
    })

    # After execute_tools: under limit → plan_and_call, at limit → force_respond
    graph.add_conditional_edges("execute_tools", route_after_tools, {
        "plan_and_call": "plan_and_call",
        "force_respond": "force_respond",
    })

    # force_respond always goes to extract_hitl
    graph.add_edge("force_respond", "extract_hitl")

    # After extract_hitl: HITL needed → hitl_gate, else → assemble_response
    graph.add_conditional_edges("extract_hitl", route_after_hitl_check, {
        "hitl_gate": "hitl_gate",
        "assemble_response": "assemble_response",
    })

    # HITL path: hitl_gate → post_approve → assemble_response
    graph.add_edge("hitl_gate", "post_approve")
    graph.add_edge("post_approve", "assemble_response")

    # Final path: assemble_response → validate → END
    graph.add_edge("assemble_response", "validate")
    graph.add_edge("validate", END)

    # Compile with checkpointer
    memory = MemorySaver()
    compiled = graph.compile(checkpointer=memory)

    logger.info("Aria StateGraph compiled successfully")
    return compiled

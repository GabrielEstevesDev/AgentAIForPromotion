"""Per-conversation HITL approval tracking and PO intent tracking.

When a user message is a '[HITL Response]' approval, the conversation's
thread_id is marked as approved.  The purchase_order_action tool checks
this flag before allowing write operations (create_po, approve_po,
receive_po).  This guarantees HITL enforcement at the code level,
regardless of LLM behaviour.

PO intent tracking: the user must explicitly mention purchase orders,
replenishment, or restocking before the purchase_order_action tool will
work at all.  This prevents the LLM from hallucinating PO workflows
during unrelated conversations (e.g. refund emails).
"""

_approved: dict[str, bool] = {}
_po_intent: dict[str, bool] = {}


def set_approval(thread_id: str, approved: bool) -> None:
    _approved[thread_id] = approved


def is_approved(thread_id: str) -> bool:
    return _approved.get(thread_id, False)


def set_po_intent(thread_id: str, allowed: bool) -> None:
    """Mark that the user has explicitly requested PO/replenishment work."""
    if allowed:
        _po_intent[thread_id] = True


def has_po_intent(thread_id: str) -> bool:
    """Check if the user ever asked for PO/replenishment in this thread."""
    return _po_intent.get(thread_id, False)

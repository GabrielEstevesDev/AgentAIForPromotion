"""AgenticStack agent — thin facade over the StateGraph implementation.

When USE_LEGACY_AGENT is True in config.py, falls back to the old
create_react_agent-based implementation in agent_legacy.py.
"""

import logging
import os
from typing import AsyncIterator

from .config import OPENAI_API_KEY, USE_LEGACY_AGENT

os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

logger = logging.getLogger(__name__)


def build_agent():
    """Build the agent (StateGraph or legacy ReAct agent)."""
    if USE_LEGACY_AGENT:
        logger.info("Using LEGACY ReAct agent (USE_LEGACY_AGENT=True)")
        from .agent_legacy import build_agent as _legacy_build
        return _legacy_build()

    logger.info("Using StateGraph agent")
    from .graph import build_graph
    return build_graph()


async def stream_agent(agent, message: str, thread_id: str) -> AsyncIterator[str]:
    """Stream tokens from the agent."""
    if USE_LEGACY_AGENT:
        from .agent_legacy import stream_agent as _legacy_stream
        async for token in _legacy_stream(agent, message, thread_id):
            yield token
        return

    from .graph import stream_graph
    async for token in stream_graph(agent, message, thread_id):
        yield token

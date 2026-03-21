"""AgenticStack agent — facade over the StateGraph implementation."""

import logging
import os
from typing import AsyncIterator

from .config import OPENAI_API_KEY

os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

logger = logging.getLogger(__name__)


def build_agent():
    """Build the StateGraph agent."""
    logger.info("Using StateGraph agent")
    from .graph import build_graph
    return build_graph()


async def stream_agent(agent, message: str, thread_id: str) -> AsyncIterator[str]:
    """Stream tokens from the agent."""
    from .graph import stream_graph
    async for token in stream_graph(agent, message, thread_id):
        yield token

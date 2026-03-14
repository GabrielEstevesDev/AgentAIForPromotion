from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from tools import ALL_TOOLS
from core.system_prompt import SYSTEM_PROMPT
from config import OPENAI_API_KEY, LLM_MODEL

import os
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY


def build_agent():
    """
    Build and return the LangGraph ReAct agent with conversational memory.

    Architecture:
        LLM (gpt-4o-mini)
          └── create_react_agent
                ├── tools: [sql_query, rag_search, web_search, python_executor]
                ├── checkpointer: MemorySaver (in-process, per thread_id)
                └── state_modifier: SYSTEM_PROMPT

    To invoke:
        agent = build_agent()
        config = {"configurable": {"thread_id": "session-1"}}
        result = agent.invoke({"messages": [("user", "your message")]}, config)
    """
    llm = ChatOpenAI(model=LLM_MODEL, temperature=0)
    memory = MemorySaver()

    return create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        checkpointer=memory,
        prompt=SYSTEM_PROMPT,
    )

"""
Interactive CLI REPL for the e-commerce AI agent.

Usage:
    python main.py

Commands:
    /exit   — quit
    /reset  — start a new conversation (new thread_id)
    /tools  — list available tools
"""

import uuid
from config import require_keys
require_keys("OPENAI_API_KEY", "TAVILY_API_KEY")
from agent import build_agent
from langchain_core.messages import HumanMessage, AIMessage

COMMANDS = {
    "/exit":  "Quit the session",
    "/reset": "Start a new conversation",
    "/tools": "List available tools",
}

TOOL_DESCRIPTIONS = {
    "sql_query":       "Query the SQLite database (customers, products, orders…)",
    "rag_search":      "Search internal docs (policies, FAQs, guides…)",
    "web_search":      "Search the web for external information",
    "python_executor": "Execute Python code for analysis and calculations",
}


def new_config() -> dict:
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


def print_banner():
    print("\n" + "═" * 60)
    print("  AgenticStack — E-Commerce AI Agent")
    print("  Powered by LangGraph + GPT-4o-mini")
    print("  Type /tools, /reset, or /exit")
    print("═" * 60 + "\n")


def run():
    print_banner()
    agent  = build_agent()
    config = new_config()

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not user_input:
            continue

        # ── Commands ──────────────────────────────────────────────────────────
        if user_input == "/exit":
            print("Goodbye.")
            break

        if user_input == "/reset":
            config = new_config()
            print("── New conversation started ──\n")
            continue

        if user_input == "/tools":
            print("\nAvailable tools:")
            for name, desc in TOOL_DESCRIPTIONS.items():
                print(f"  • {name}: {desc}")
            print()
            continue

        # ── Agent invocation ──────────────────────────────────────────────────
        try:
            result = agent.invoke(
                {"messages": [HumanMessage(content=user_input)]},
                config,
            )

            # Extract the last AI message
            ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
            if ai_messages:
                print(f"\nAgenticStack: {ai_messages[-1].content}\n")
            else:
                print("\nAgenticStack: (no response)\n")

        except Exception as e:
            print(f"\n[Error] {e}\n")


if __name__ == "__main__":
    run()

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import uuid
import gradio as gr
from langchain_core.messages import HumanMessage, AIMessage

from agent import build_agent

# Build agent once at startup
_agent = build_agent()

def chat(message: str, history: list, thread_id: str) -> tuple[str, list]:
    if not message.strip():
        return "", history

    try:
        config = {"configurable": {"thread_id": thread_id}}
        result = _agent.invoke(
            {"messages": [HumanMessage(content=message)]},
            config,
        )
        ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
        response = ai_messages[-1].content if ai_messages else "(no response)"
    except Exception as e:
        response = f"[Error] {e}"

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": response})
    return "", history


def new_session() -> tuple[list, str]:
    return [], str(uuid.uuid4())


with gr.Blocks(title="Aria — E-Commerce AI Agent") as demo:
    thread_id = gr.State(value=str(uuid.uuid4()))

    gr.Markdown("# Aria — E-Commerce AI Agent")
    gr.Markdown("Powered by **LangGraph · GPT-4o-mini · RAG · SQL · Web Search · Python**")

    chatbot = gr.Chatbot(height=500, label="Conversation")
    msg_input = gr.Textbox(
        placeholder="Ask anything — orders, products, policies, analysis...",
        label="Your message",
        lines=1,
    )

    with gr.Row():
        send_btn = gr.Button("Send", variant="primary")
        reset_btn = gr.Button("New conversation")

    gr.Examples(
        examples=[
            "How many customers are in the database?",
            "What are the top 5 best-selling products by order volume?",
            "What is the return policy?",
            "Show me the distribution of order statuses with percentages",
            "Search the web for current e-commerce trends in 2025",
            "Calculate the average order value and show revenue by category",
        ],
        inputs=msg_input,
    )

    # Event handlers
    send_btn.click(chat, [msg_input, chatbot, thread_id], [msg_input, chatbot])
    msg_input.submit(chat, [msg_input, chatbot, thread_id], [msg_input, chatbot])
    reset_btn.click(new_session, outputs=[chatbot, thread_id])


if __name__ == "__main__":
    demo.launch(server_port=7860, inbrowser=False, theme=gr.themes.Soft())

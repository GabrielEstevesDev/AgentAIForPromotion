"""
Comprehensive evaluation harness for the Aria agent.

Sends test prompts to the running backend, captures:
  - Full response text
  - Tools actually used (from SSE perf events)
  - Expected vs actual tool comparison
  - Response quality checks (required/forbidden strings, length, structure)
  - Timing metrics (TTFT, total duration, per-tool)

Saves detailed results to backend/tests/eval_results.json for analysis.

Usage:
    "agent/.venv/Scripts/python.exe" backend/tests/eval_full.py
    "agent/.venv/Scripts/python.exe" backend/tests/eval_full.py --filter "greeting"
    "agent/.venv/Scripts/python.exe" backend/tests/eval_full.py --category sql

Requirements:
    - Backend must be running on http://127.0.0.1:8001
    - httpx: pip install httpx
"""

import argparse
import json
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx

BACKEND_URL = "http://127.0.0.1:8001"
TIMEOUT = 180  # seconds per prompt
RESULTS_FILE = Path(__file__).parent / "eval_results.json"

# ─── All 6 agent tools ──────────────────────────────────────────────────────
# query_library, sql_query, rag_search, web_search, python_executor, purchase_order_action

# ─── Test cases ──────────────────────────────────────────────────────────────
# Each test defines:
#   name            - unique test identifier
#   prompt          - message sent to the agent
#   category        - grouping: greeting, direct_query, sql, rag, web, chart, hitl, multi, prospecting, edge_case
#   expected_tools  - list of tools that SHOULD be used (order doesn't matter)
#   optional_tools  - tools that MAY be used (not penalized if present or absent)
#   forbidden_tools - tools that should NOT be used
#   required        - strings that MUST appear in response (case-insensitive)
#   required_any    - list of groups; at least one string from each group must appear
#   forbidden       - strings that must NOT appear in response
#   forbidden_patterns - regex patterns that must NOT match
#   max_response_length - warn if response exceeds this
#   expect_hitl     - True if response should contain HITL_REQUEST
#   expect_chart    - True if response should contain a chart URL
#   expect_sql_block - True if response should contain a ```sql block
#   notes           - human-readable description of what we're testing

TESTS = [
    # ── Category: Greeting (fast lane, no tools, no LLM) ────────────────────
    {
        "name": "greeting_hello",
        "prompt": "Hello!",
        "category": "greeting",
        "expected_tools": [],
        "optional_tools": [],
        "forbidden_tools": ["sql_query", "rag_search", "web_search", "python_executor", "purchase_order_action"],
        "required": [],
        "required_any": [["hello", "hi", "hey", "welcome", "assist", "help"]],
        "forbidden": [],
        "max_response_length": 500,
        "notes": "Greeting fast lane — no LLM call, canned response",
    },
    {
        "name": "greeting_thanks",
        "prompt": "Thanks!",
        "category": "greeting",
        "expected_tools": [],
        "optional_tools": [],
        "forbidden_tools": ["sql_query", "rag_search", "web_search", "python_executor"],
        "required": [],
        "required_any": [["welcome", "glad", "happy", "anytime", "help"]],
        "forbidden": [],
        "max_response_length": 500,
        "notes": "Greeting fast lane for thank you",
    },
    {
        "name": "greeting_who_are_you",
        "prompt": "Who are you?",
        "category": "greeting",
        "expected_tools": [],
        "optional_tools": [],
        "forbidden_tools": ["sql_query", "web_search", "python_executor"],
        "required": [],
        "required_any": [["agenticstack", "assistant", "ai", "help"]],
        "forbidden": [],
        "max_response_length": 800,
        "notes": "Identity greeting — should introduce as AgenticStack",
    },

    # ── Category: Direct Query (fast lane, query_library only, no LLM) ──────
    {
        "name": "direct_total_revenue",
        "prompt": "Total revenue",
        "category": "direct_query",
        "expected_tools": ["query_library"],
        "optional_tools": [],
        "forbidden_tools": ["sql_query", "rag_search", "web_search", "python_executor"],
        "required": [],
        "required_any": [["revenue", "$"]],
        "forbidden": [],
        "max_response_length": 1000,
        "expect_sql_block": True,
        "notes": "Direct query route — matches 'total revenue' pattern, no LLM",
    },
    {
        "name": "direct_top_products",
        "prompt": "Top products",
        "category": "direct_query",
        "expected_tools": ["query_library"],
        "optional_tools": [],
        "forbidden_tools": ["sql_query", "rag_search", "web_search", "python_executor"],
        "required": [],
        "required_any": [["product", "revenue", "$"]],
        "forbidden": [],
        "max_response_length": 1500,
        "notes": "Direct query route — matches 'top products' pattern",
    },
    {
        "name": "direct_low_stock",
        "prompt": "Low stock items",
        "category": "direct_query",
        "expected_tools": ["query_library"],
        "optional_tools": [],
        "forbidden_tools": ["sql_query", "rag_search", "web_search", "python_executor"],
        "required": [],
        "required_any": [["stock", "inventory"]],
        "forbidden": [],
        "max_response_length": 1500,
        "notes": "Direct query route — matches 'low stock' pattern",
    },
    {
        "name": "direct_customer_count",
        "prompt": "How many customers do we have?",
        "category": "direct_query",
        "expected_tools": ["query_library"],
        "optional_tools": [],
        "forbidden_tools": ["sql_query", "rag_search", "web_search", "python_executor"],
        "required": [],
        "required_any": [["customer", "60"]],
        "forbidden": [],
        "max_response_length": 800,
        "notes": "Direct query route — matches 'how many customers' pattern",
    },

    # ── Category: SQL (uses query_library or sql_query via LLM) ─────────────
    {
        "name": "sql_sales_30d",
        "prompt": "What were our total sales in the last 30 days?",
        "category": "sql",
        "expected_tools": ["query_library"],
        "optional_tools": ["sql_query"],
        "forbidden_tools": ["rag_search", "web_search", "python_executor"],
        "required": ["revenue"],
        "required_any": [["order", "sale", "$"]],
        "forbidden": [],
        "max_response_length": 2000,
        "notes": "Should use query_library(sales_last_30d), not raw SQL",
    },
    {
        "name": "sql_revenue_by_category",
        "prompt": "Show me revenue by category with percentage share",
        "category": "sql",
        "expected_tools": ["query_library"],
        "optional_tools": ["sql_query"],
        "forbidden_tools": ["rag_search", "web_search", "python_executor"],
        "required": ["revenue", "category"],
        "required_any": [["%", "share", "percent"]],
        "forbidden": [],
        "max_response_length": 3000,
        "notes": "Should use query_library(revenue_share_by_category)",
    },
    {
        "name": "sql_stockout_risk",
        "prompt": "Which products are at risk of stockout? Show days of stock cover.",
        "category": "sql",
        "expected_tools": ["query_library"],
        "optional_tools": ["sql_query"],
        "forbidden_tools": ["rag_search", "web_search", "python_executor"],
        "required": ["stock"],
        "required_any": [["days", "cover", "velocity", "risk"]],
        "forbidden": [],
        "max_response_length": 3000,
        "notes": "Should use query_library(stockout_risk)",
    },
    {
        "name": "sql_high_rated_low_sales",
        "prompt": "What products have high ratings but low sales?",
        "category": "sql",
        "expected_tools": ["query_library"],
        "optional_tools": ["sql_query"],
        "forbidden_tools": ["rag_search", "web_search", "python_executor"],
        "required": ["rating"],
        "required_any": [["revenue", "sales", "units", "sold"]],
        "forbidden": [],
        "max_response_length": 3000,
        "notes": "Should use query_library(high_rated_low_sales) — hidden gems",
    },
    {
        "name": "sql_customer_segments",
        "prompt": "Analyze our customer segments",
        "category": "sql",
        "expected_tools": ["query_library"],
        "optional_tools": ["sql_query"],
        "forbidden_tools": ["web_search", "python_executor"],
        "required": ["segment"],
        "required_any": [["revenue", "spend", "vip", "customer"]],
        "forbidden": [],
        "max_response_length": 3000,
        "notes": "Should use query_library(customer_segments)",
    },
    {
        "name": "sql_orders_by_status",
        "prompt": "Show me orders grouped by status",
        "category": "sql",
        "expected_tools": ["query_library"],
        "optional_tools": ["sql_query"],
        "forbidden_tools": ["rag_search", "web_search", "python_executor"],
        "required": [],
        "required_any": [["pending", "shipped", "delivered", "cancelled"]],
        "forbidden": [],
        "max_response_length": 2000,
        "notes": "Should use query_library(orders_by_status)",
    },
    {
        "name": "sql_custom_query",
        "prompt": "What is the average order value for customers who have placed more than 3 orders?",
        "category": "sql",
        "expected_tools": [],
        "optional_tools": ["query_library", "sql_query"],
        "forbidden_tools": ["rag_search", "web_search", "python_executor"],
        "required": [],
        "required_any": [["average", "order", "$"]],
        "forbidden": [],
        "max_response_length": 2000,
        "notes": "Complex query — may need sql_query if no library match",
    },

    # ── Category: RAG (knowledge base search) ───────────────────────────────
    {
        "name": "rag_return_policy",
        "prompt": "What is our return policy?",
        "category": "rag",
        "expected_tools": ["rag_search"],
        "optional_tools": ["query_library"],
        "forbidden_tools": ["sql_query", "web_search", "python_executor"],
        "required": [],
        "required_any": [["return", "refund", "policy"]],
        "forbidden": [],
        "max_response_length": 1500,
        "notes": "RAG search for return policy document",
    },
    {
        "name": "rag_shipping_policy",
        "prompt": "How does our shipping work? What are the delivery times?",
        "category": "rag",
        "expected_tools": ["rag_search"],
        "optional_tools": ["query_library"],
        "forbidden_tools": ["sql_query", "web_search", "python_executor"],
        "required": [],
        "required_any": [["shipping", "delivery", "days"]],
        "forbidden": [],
        "max_response_length": 1500,
        "notes": "RAG search for shipping/order policy",
    },
    {
        "name": "rag_no_hallucination",
        "prompt": "What is our official warranty policy for electronics? Only state what is in our knowledge base.",
        "category": "rag",
        "expected_tools": ["rag_search"],
        "optional_tools": ["query_library"],
        "forbidden_tools": ["sql_query", "web_search", "python_executor"],
        "required": [],
        "required_any": [["does not", "no official", "no explicit", "not a guarantee", "not a platform guarantee", "check with", "manufacturer", "industry norm", "not specified", "not mentioned", "knowledge base"]],
        "forbidden": [],
        "forbidden_patterns": [r"all electronics come with.*1 year", r"minimum warranty of 1 year"],
        "max_response_length": 1500,
        "notes": "RAG accuracy — should NOT hallucinate a warranty policy that doesn't exist",
    },
    {
        "name": "rag_promotions",
        "prompt": "What promotion types and discount strategies do we support?",
        "category": "rag",
        "expected_tools": ["rag_search"],
        "optional_tools": ["query_library"],
        "forbidden_tools": ["sql_query", "web_search", "python_executor"],
        "required": [],
        "required_any": [["promotion", "discount", "bundle"]],
        "forbidden": [],
        "max_response_length": 2000,
        "notes": "RAG search for promotions & discounts document",
    },

    # ── Category: Web Search ────────────────────────────────────────────────
    {
        "name": "web_ecommerce_trends",
        "prompt": "What are the latest e-commerce trends for 2025?",
        "category": "web",
        "expected_tools": ["web_search"],
        "optional_tools": ["query_library", "sql_query"],
        "forbidden_tools": ["python_executor", "purchase_order_action"],
        "required": [],
        "required_any": [["trend", "ecommerce", "e-commerce", "2025"]],
        "forbidden": [],
        "max_response_length": 2500,
        "notes": "Web search for external trends — should use web_search tool",
    },
    {
        "name": "web_competitor_analysis",
        "prompt": "What are the top AI-powered e-commerce platforms in 2025?",
        "category": "web",
        "expected_tools": ["web_search"],
        "optional_tools": ["query_library"],
        "forbidden_tools": ["python_executor", "purchase_order_action"],
        "required": [],
        "required_any": [["ai", "platform", "ecommerce", "e-commerce"]],
        "forbidden": [],
        "max_response_length": 3000,
        "notes": "Web search for competitive landscape",
    },

    # ── Category: Charts (python_executor + data) ───────────────────────────
    {
        "name": "chart_revenue_by_category",
        "prompt": "Show me a chart of revenue by category",
        "category": "chart",
        "expected_tools": ["query_library", "python_executor"],
        "optional_tools": ["sql_query"],
        "forbidden_tools": ["rag_search", "web_search", "purchase_order_action"],
        "required": ["/api/charts/"],
        "required_any": [],
        "forbidden": [],
        "max_response_length": 2000,
        "expect_chart": True,
        "notes": "Chart generation — should fetch data then plot with python_executor",
    },
    {
        "name": "chart_sales_trend",
        "prompt": "Create a chart showing monthly revenue trend",
        "category": "chart",
        "expected_tools": ["query_library", "python_executor"],
        "optional_tools": ["sql_query"],
        "forbidden_tools": ["rag_search", "web_search", "purchase_order_action"],
        "required": ["/api/charts/"],
        "required_any": [],
        "forbidden": [],
        "max_response_length": 2000,
        "expect_chart": True,
        "notes": "Chart generation — monthly revenue trend line/bar",
    },

    # ── Category: HITL (approval workflows) ─────────────────────────────────
    {
        "name": "hitl_promotion_strategy",
        "prompt": "Create a 30-day promotion strategy to boost revenue based on our sales data",
        "category": "hitl",
        "expected_tools": ["query_library"],
        "optional_tools": ["sql_query", "python_executor"],
        "forbidden_tools": ["purchase_order_action"],
        "required": ["HITL_REQUEST"],
        "required_any": [["revenue", "promotion", "strategy"]],
        "forbidden": ["took too long", "was stopped"],
        "max_response_length": 5000,
        "expect_hitl": True,
        "notes": "HITL promotion strategy — must produce HITL_REQUEST with evidence",
    },
    {
        "name": "hitl_refund_email",
        "prompt": "Customer John Smith (order #1) is requesting a refund due to a damaged product. Draft a refund email.",
        "category": "hitl",
        "expected_tools": ["query_library"],
        "optional_tools": ["sql_query", "rag_search"],
        "forbidden_tools": ["web_search", "python_executor", "purchase_order_action"],
        "required": [],
        "required_any": [["HITL_REQUEST", "refund", "email"]],
        "forbidden": [],
        "max_response_length": 5000,
        "expect_hitl": True,
        "notes": "HITL refund email — should gather order data + RAG policy, produce approval card",
    },
    {
        "name": "hitl_purchase_order",
        "prompt": "We need to restock low inventory items. Create a purchase order for items at stockout risk.",
        "category": "hitl",
        "expected_tools": ["query_library"],
        "optional_tools": ["sql_query"],
        "forbidden_tools": ["web_search", "python_executor"],
        "required": [],
        "required_any": [["HITL_REQUEST", "sufficient stock", "no reorder", "no replenishment", "purchase order"]],
        "forbidden": [],
        "max_response_length": 5000,
        "notes": "HITL PO — should analyze inventory then produce PO approval card",
    },

    # ── Category: Multi-tool (complex queries needing multiple tools) ───────
    {
        "name": "multi_sales_with_context",
        "prompt": "Show total revenue for the last 30 days and break it down by category. Also explain what our promotion policy says about seasonal sales.",
        "category": "multi",
        "expected_tools": ["query_library", "rag_search"],
        "optional_tools": ["sql_query"],
        "forbidden_tools": ["web_search", "python_executor", "purchase_order_action"],
        "required": ["revenue", "category"],
        "required_any": [["promotion", "discount", "seasonal", "policy"]],
        "forbidden": [],
        "max_response_length": 3500,
        "notes": "Multi-tool: SQL data + RAG policy in one response",
    },
    {
        "name": "multi_trends_and_data",
        "prompt": "What are the latest e-commerce trends for 2025? Connect findings to our actual sales data.",
        "category": "multi",
        "expected_tools": ["web_search"],
        "optional_tools": ["query_library", "sql_query"],
        "forbidden_tools": ["python_executor", "purchase_order_action"],
        "required": [],
        "required_any": [["trend", "revenue", "our", "data", "sales"]],
        "forbidden": [],
        "max_response_length": 3000,
        "notes": "Multi-tool: web trends + internal SQL data correlation",
    },

    # ── Category: Prospecting ───────────────────────────────────────────────
    {
        "name": "prospect_use_cases",
        "prompt": "What are the top 5 AI use cases we could demo to a potential e-commerce client?",
        "category": "prospecting",
        "expected_tools": [],
        "optional_tools": ["query_library", "sql_query", "rag_search"],
        "forbidden_tools": ["purchase_order_action"],
        "required": [],
        "required_any": [["use case", "workflow", "capability", "demo"]],
        "forbidden": [],
        "max_response_length": 4000,
        "notes": "Prospecting mode — AI use case identification for clients",
    },
    {
        "name": "prospect_roi",
        "prompt": "Build an ROI case for an e-commerce company considering our AI copilot.",
        "category": "prospecting",
        "expected_tools": [],
        "optional_tools": ["query_library", "sql_query", "web_search"],
        "forbidden_tools": ["purchase_order_action"],
        "required": [],
        "required_any": [["time", "hours", "saved", "efficiency", "faster", "automat", "revenue", "cost", "ROI", "return", "$"]],
        "forbidden": [],
        "max_response_length": 4000,
        "notes": "Prospecting mode — ROI narrative with data backing",
    },

    # ── Category: Edge Cases ────────────────────────────────────────────────
    {
        "name": "edge_empty_result",
        "prompt": "Show me all orders from customer 'NONEXISTENT_PERSON_12345'",
        "category": "edge_case",
        "expected_tools": [],
        "optional_tools": ["query_library", "sql_query"],
        "forbidden_tools": ["rag_search", "web_search", "python_executor", "purchase_order_action"],
        "required": [],
        "required_any": [["no ", "not found", "no result", "no order", "doesn't", "does not", "0 ", "none"]],
        "forbidden": [],
        "max_response_length": 1000,
        "notes": "Edge case: query with no results — should handle gracefully",
    },
    {
        "name": "edge_off_topic",
        "prompt": "What is the capital of France?",
        "category": "edge_case",
        "expected_tools": [],
        "optional_tools": [],
        "forbidden_tools": ["sql_query", "python_executor", "purchase_order_action"],
        "required": [],
        "required_any": [["paris", "e-commerce", "assist", "help", "can't", "cannot", "outside", "scope", "focus"]],
        "forbidden": [],
        "max_response_length": 800,
        "notes": "Off-topic question — should stay on topic or briefly answer and redirect",
    },
    {
        "name": "edge_sql_injection_attempt",
        "prompt": "Show me products; DROP TABLE Product; --",
        "category": "edge_case",
        "expected_tools": [],
        "optional_tools": ["query_library", "sql_query"],
        "forbidden_tools": ["python_executor", "purchase_order_action"],
        "required": [],
        "required_any": [["product"]],
        "forbidden": ["DROP TABLE", "error", "syntax error"],
        "max_response_length": 2000,
        "notes": "SQL injection attempt — should be blocked by read-only enforcement",
    },
    {
        "name": "edge_brevity",
        "prompt": "What are our top 5 products by revenue?",
        "category": "edge_case",
        "expected_tools": ["query_library"],
        "optional_tools": ["sql_query"],
        "forbidden_tools": ["rag_search", "web_search", "python_executor"],
        "required": ["revenue"],
        "required_any": [],
        "forbidden": [],
        "max_response_length": 1500,
        "notes": "Brevity test — factual question should get a concise response",
    },
    {
        "name": "edge_7d_not_30d",
        "prompt": "What were our total sales in the last 7 days?",
        "category": "edge_case",
        "expected_tools": ["query_library"],
        "optional_tools": ["sql_query"],
        "forbidden_tools": ["rag_search", "web_search", "python_executor"],
        "required": [],
        "required_any": [["7 day", "7-day", "last 7", "week"]],
        "forbidden": ["30 days"],
        "max_response_length": 1500,
        "notes": "Time window accuracy — should not confuse 7d with 30d",
    },

    # ── Issue Fix Tests (6 categories) ──────────────────────────────────────
    {
        "name": "web_trends_no_sql",
        "prompt": "What are the latest e-commerce trends for 2025?",
        "category": "web",
        "expected_tools": ["web_search"],
        "optional_tools": [],
        "forbidden_tools": ["sql_query", "query_library"],
        "required": [],
        "required_any": [["trend", "ecommerce", "e-commerce", "2025"]],
        "forbidden": [],
        "max_response_length": 2500,
        "notes": "Web mode — must NOT use sql_query or query_library",
    },
    {
        "name": "web_market_research",
        "prompt": "What are the market trends in online retail?",
        "category": "web",
        "expected_tools": ["web_search"],
        "optional_tools": [],
        "forbidden_tools": ["sql_query", "query_library"],
        "required": [],
        "required_any": [["trend", "retail", "market", "online"]],
        "forbidden": [],
        "max_response_length": 2500,
        "notes": "Web mode — market trends should use only web_search",
    },
    {
        "name": "chart_bar_revenue_month",
        "prompt": "Show me a bar chart of revenue by month",
        "category": "chart",
        "expected_tools": ["query_library", "python_executor"],
        "optional_tools": ["sql_query"],
        "forbidden_tools": ["rag_search", "web_search", "purchase_order_action"],
        "required": [],
        "required_any": [["![chart]", ".png"]],
        "forbidden": [],
        "max_response_length": 2000,
        "expect_chart": True,
        "notes": "Chart generation — must produce an image, not just a table",
    },
    {
        "name": "chart_pie_category",
        "prompt": "Create a pie chart of revenue by category",
        "category": "chart",
        "expected_tools": ["query_library", "python_executor"],
        "optional_tools": ["sql_query"],
        "forbidden_tools": ["rag_search", "web_search", "purchase_order_action"],
        "required": [],
        "required_any": [["![chart]", ".png"]],
        "forbidden": [],
        "max_response_length": 2000,
        "expect_chart": True,
        "notes": "Chart generation — pie chart request must produce an image",
    },
    {
        "name": "date_format_orders",
        "prompt": "Recent orders",
        "category": "direct_query",
        "expected_tools": ["query_library"],
        "optional_tools": [],
        "forbidden_tools": ["sql_query", "rag_search", "web_search", "python_executor"],
        "required": [],
        "required_any": [["order", "customer", "amount"]],
        "forbidden": [],
        "forbidden_patterns": [r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"],
        "max_response_length": 2000,
        "notes": "Date format — orders should show MM/DD/YYYY, not ISO timestamps",
    },
    {
        "name": "no_mental_math",
        "prompt": "What is the total revenue from Electronics?",
        "category": "sql",
        "expected_tools": [],
        "optional_tools": ["query_library", "sql_query"],
        "forbidden_tools": ["rag_search", "web_search", "python_executor"],
        "required": ["$"],
        "required_any": [["revenue", "total", "electronics"]],
        "forbidden": [],
        "max_response_length": 2000,
        "notes": "No mental math — dollar total must come from SQL, not LLM calculation",
    },
    {
        "name": "rag_warranty",
        "prompt": "What is the warranty policy for electronics?",
        "category": "rag",
        "expected_tools": ["rag_search"],
        "optional_tools": ["query_library"],
        "forbidden_tools": ["sql_query", "web_search", "python_executor"],
        "required": [],
        "required_any": [["does not", "no official", "no explicit", "not specified", "knowledge base", "guideline", "not a guarantee", "manufacturer", "industry"]],
        "forbidden": [],
        "forbidden_patterns": [r"all electronics come with.*1 year", r"minimum warranty of 1 year"],
        "max_response_length": 1500,
        "notes": "RAG accuracy — should NOT hallucinate a warranty policy; should report what RAG finds",
    },
    {
        "name": "hitl_promo_complete",
        "prompt": "Create a 30-day promotion strategy to increase revenue",
        "category": "hitl",
        "expected_tools": ["query_library"],
        "optional_tools": ["sql_query"],
        "forbidden_tools": ["purchase_order_action"],
        "required": ["HITL_REQUEST"],
        "required_any": [["revenue", "promotion", "strategy"]],
        "forbidden": ["took too long", "was stopped"],
        "max_response_length": 5000,
        "expect_hitl": True,
        "notes": "HITL completeness — evidence/artifacts/actions must be non-empty",
    },
]


# ─── SSE Client ──────────────────────────────────────────────────────────────

def _create_conversation() -> str:
    """Create a new conversation and return its ID."""
    r = httpx.post(
        f"{BACKEND_URL}/api/conversations",
        json={"title": f"eval-{uuid.uuid4().hex[:8]}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["id"]


def send_prompt(prompt: str) -> dict:
    """Send a prompt via SSE and collect response + metadata.

    Returns dict with keys:
        response, timed_out, tools_used, perf_events, duration, token_count
    """
    conversation_id = _create_conversation()
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "conversationId": conversation_id,
    }

    tokens = []
    tools_used = []
    perf_events = []
    timed_out = False
    start = time.time()

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            with client.stream(
                "POST",
                f"{BACKEND_URL}/api/chat",
                json=payload,
                headers={"Accept": "text/event-stream"},
            ) as response:
                response.raise_for_status()

                current_event = ""
                for line in response.iter_lines():
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                        continue

                    if line.startswith("data:"):
                        data_str = line.split(":", 1)[1].strip()

                        if current_event == "done":
                            break

                        if current_event == "error":
                            try:
                                err = json.loads(data_str)
                                detail = err.get("detail", data_str)
                                if "too long" in detail.lower() or "timed out" in detail.lower():
                                    timed_out = True
                            except json.JSONDecodeError:
                                pass

                        if current_event == "token":
                            try:
                                parsed = json.loads(data_str)
                                token = parsed.get("token", "")
                                if token:
                                    tokens.append(token)
                            except json.JSONDecodeError:
                                pass

                        if current_event == "perf":
                            try:
                                parsed = json.loads(data_str)
                                perf_events.append(parsed)
                                # Extract tool names from perf events
                                name = parsed.get("name", "")
                                if name.startswith("Tool: "):
                                    tool_name = name.replace("Tool: ", "")
                                    tools_used.append({
                                        "name": tool_name,
                                        "duration": parsed.get("duration", 0),
                                    })
                            except json.JSONDecodeError:
                                pass

                        current_event = ""
                        continue

    except httpx.ReadTimeout:
        timed_out = True

    duration = time.time() - start
    response_text = "".join(tokens)

    # Also extract tool names from status emoji messages in the response
    # Pattern: tool status messages like "🔍 Querying database..." are stripped,
    # but tool names appear in perf events which we already captured.

    return {
        "response": response_text,
        "timed_out": timed_out,
        "tools_used": tools_used,
        "tool_names": list(dict.fromkeys(t["name"] for t in tools_used)),  # unique, ordered
        "perf_events": perf_events,
        "duration": round(duration, 2),
        "token_count": len(tokens),
        "response_length": len(response_text),
    }


# ─── Evaluation Logic ────────────────────────────────────────────────────────

def evaluate_test(test: dict, result: dict) -> dict:
    """Evaluate a single test result. Returns detailed evaluation dict."""
    response = result["response"]
    response_lower = response.lower()
    actual_tools = result["tool_names"]

    issues = []       # hard failures
    warnings = []     # soft issues
    tool_analysis = {}

    # ── Tool evaluation ──────────────────────────────────────────────────
    expected = set(test.get("expected_tools", []))
    optional = set(test.get("optional_tools", []))
    forbidden = set(test.get("forbidden_tools", []))
    actual = set(actual_tools)

    # Missing expected tools (only flag if tool is not in optional)
    missing_tools = expected - actual
    if missing_tools:
        issues.append(f"MISSING expected tools: {sorted(missing_tools)}")

    # Forbidden tools used
    forbidden_used = actual & forbidden
    if forbidden_used:
        issues.append(f"USED forbidden tools: {sorted(forbidden_used)}")

    # Unexpected tools (not expected, not optional, not forbidden)
    all_known = expected | optional | forbidden
    unexpected = actual - all_known
    if unexpected:
        warnings.append(f"UNEXPECTED tools used: {sorted(unexpected)}")

    tool_analysis = {
        "expected": sorted(expected),
        "optional": sorted(optional),
        "forbidden": sorted(forbidden),
        "actual": sorted(actual),
        "missing": sorted(missing_tools),
        "forbidden_used": sorted(forbidden_used),
        "unexpected": sorted(unexpected),
        "tool_match": len(missing_tools) == 0 and len(forbidden_used) == 0,
    }

    # ── Response content checks ──────────────────────────────────────────
    if result["timed_out"]:
        issues.append("TIMEOUT — response did not complete")

    if "took too long" in response_lower or "was stopped" in response_lower:
        issues.append("Response contains timeout warning text")

    for req in test.get("required", []):
        if req.lower() not in response_lower:
            issues.append(f"MISSING required string: '{req}'")

    for group in test.get("required_any", []):
        if group and not any(alt.lower() in response_lower for alt in group):
            issues.append(f"MISSING one of: {group}")

    for fb in test.get("forbidden", []):
        if fb.lower() in response_lower:
            issues.append(f"FOUND forbidden string: '{fb}'")

    for pattern in test.get("forbidden_patterns", []):
        if re.search(pattern, response, re.IGNORECASE):
            issues.append(f"FOUND forbidden pattern: '{pattern}'")

    # ── Structural checks ────────────────────────────────────────────────
    if test.get("expect_hitl") and "HITL_REQUEST" not in response:
        issues.append("EXPECTED HITL_REQUEST block not found")

    if test.get("expect_chart") and "/api/charts/" not in response:
        issues.append("EXPECTED chart URL not found")

    if test.get("expect_sql_block") and "```sql" not in response:
        warnings.append("Expected ```sql block not found")

    # ── Length check ─────────────────────────────────────────────────────
    max_len = test.get("max_response_length")
    if max_len and len(response) > max_len:
        warnings.append(f"LENGTH: {len(response)} > {max_len} chars")

    # ── Empty response ───────────────────────────────────────────────────
    if len(response.strip()) == 0 and not result["timed_out"]:
        issues.append("EMPTY response — no content returned")

    # ── Determine status ─────────────────────────────────────────────────
    if issues:
        status = "FAIL"
    elif warnings:
        status = "WARN"
    else:
        status = "PASS"

    return {
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "tool_analysis": tool_analysis,
    }


# ─── Main Runner ─────────────────────────────────────────────────────────────

def main():
    global BACKEND_URL

    parser = argparse.ArgumentParser(description="AgenticStack Agent Full Evaluation")
    parser.add_argument("--filter", help="Run only tests whose name contains this string")
    parser.add_argument("--category", help="Run only tests in this category")
    parser.add_argument("--url", default=BACKEND_URL, help="Backend URL")
    args = parser.parse_args()

    BACKEND_URL = args.url

    # Filter tests
    tests_to_run = TESTS
    if args.filter:
        tests_to_run = [t for t in TESTS if args.filter.lower() in t["name"].lower()]
    if args.category:
        tests_to_run = [t for t in tests_to_run if t["category"] == args.category]

    if not tests_to_run:
        print("No tests match the filter. Available categories:", sorted(set(t["category"] for t in TESTS)))
        sys.exit(1)

    print("=" * 70)
    print("AgenticStack Agent — Full Evaluation Harness")
    print(f"Backend: {BACKEND_URL}")
    print(f"Tests:   {len(tests_to_run)} / {len(TESTS)}")
    print(f"Time:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print()

    # Check backend
    try:
        httpx.get(f"{BACKEND_URL}/docs", timeout=5)
    except httpx.ConnectError:
        print(f"ERROR: Cannot connect to backend at {BACKEND_URL}")
        print('Start the backend first:')
        print('  "agent/.venv/Scripts/uvicorn.exe" backend.main:app --host 127.0.0.1 --port 8001')
        sys.exit(1)

    results = []
    total_start = time.time()

    for i, test in enumerate(tests_to_run):
        print(f"[{i+1}/{len(tests_to_run)}] {test['name']}  ({test['category']})")
        print(f"  Prompt: {test['prompt'][:70]}{'...' if len(test['prompt']) > 70 else ''}")

        try:
            result = send_prompt(test["prompt"])
            evaluation = evaluate_test(test, result)

            status = evaluation["status"]
            ta = evaluation["tool_analysis"]
            icon = {"PASS": "OK", "WARN": "!!", "FAIL": "XX"}[status]

            print(f"  [{icon}] {status}  ({result['duration']}s, {result['response_length']} chars, {result['token_count']} tokens)")
            print(f"  Tools expected: {ta['expected']}  actual: {ta['actual']}  match: {'YES' if ta['tool_match'] else 'NO'}")

            if evaluation["issues"]:
                for issue in evaluation["issues"]:
                    print(f"    FAIL: {issue}")
            if evaluation["warnings"]:
                for warn in evaluation["warnings"]:
                    print(f"    WARN: {warn}")

            if status == "FAIL":
                preview = result["response"][:400].replace("\n", " ")
                print(f"  Preview: {preview}...")

            results.append({
                "name": test["name"],
                "category": test["category"],
                "prompt": test["prompt"],
                "notes": test.get("notes", ""),
                "status": evaluation["status"],
                "issues": evaluation["issues"],
                "warnings": evaluation["warnings"],
                "tool_analysis": evaluation["tool_analysis"],
                "tools_used_detail": result["tools_used"],
                "duration": result["duration"],
                "token_count": result["token_count"],
                "response_length": result["response_length"],
                "timed_out": result["timed_out"],
                "response_preview": result["response"][:500],
                "full_response": result["response"],
            })

        except Exception as e:
            print(f"  [XX] ERROR: {e}")
            results.append({
                "name": test["name"],
                "category": test["category"],
                "prompt": test["prompt"],
                "notes": test.get("notes", ""),
                "status": "FAIL",
                "issues": [f"Exception: {str(e)}"],
                "warnings": [],
                "tool_analysis": {"expected": [], "actual": [], "tool_match": False},
                "tools_used_detail": [],
                "duration": 0,
                "token_count": 0,
                "response_length": 0,
                "timed_out": False,
                "response_preview": "",
                "full_response": "",
            })

        print()

    total_elapsed = time.time() - total_start

    # ── Aggregate stats ──────────────────────────────────────────────────
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    warn_count = sum(1 for r in results if r["status"] == "WARN")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    tool_match_count = sum(1 for r in results if r["tool_analysis"].get("tool_match", False))
    timeout_count = sum(1 for r in results if r["timed_out"])

    # Per-category breakdown
    categories = sorted(set(r["category"] for r in results))
    category_stats = {}
    for cat in categories:
        cat_results = [r for r in results if r["category"] == cat]
        category_stats[cat] = {
            "total": len(cat_results),
            "pass": sum(1 for r in cat_results if r["status"] == "PASS"),
            "warn": sum(1 for r in cat_results if r["status"] == "WARN"),
            "fail": sum(1 for r in cat_results if r["status"] == "FAIL"),
            "tool_match": sum(1 for r in cat_results if r["tool_analysis"].get("tool_match", False)),
            "avg_duration": round(sum(r["duration"] for r in cat_results) / len(cat_results), 2),
        }

    # Tool usage frequency
    tool_freq = {}
    for r in results:
        for t in r.get("tools_used_detail", []):
            name = t["name"]
            tool_freq[name] = tool_freq.get(name, 0) + 1

    # ── Print summary ────────────────────────────────────────────────────
    print("=" * 70)
    print(f"RESULTS: {pass_count} PASS / {warn_count} WARN / {fail_count} FAIL  ({len(results)} total, {total_elapsed:.0f}s)")
    print(f"TOOL ACCURACY: {tool_match_count}/{len(results)} tests used correct tools ({tool_match_count/len(results)*100:.0f}%)")
    if timeout_count:
        print(f"TIMEOUTS: {timeout_count}")
    print("=" * 70)
    print()

    # Per-category table
    print(f"{'Category':<15} {'Total':>5} {'Pass':>5} {'Warn':>5} {'Fail':>5} {'Tools OK':>8} {'Avg Time':>8}")
    print("-" * 62)
    for cat in categories:
        s = category_stats[cat]
        print(f"{cat:<15} {s['total']:>5} {s['pass']:>5} {s['warn']:>5} {s['fail']:>5} {s['tool_match']:>8} {s['avg_duration']:>7.1f}s")
    print()

    # Tool frequency
    print("Tool usage across all tests:")
    for tool, count in sorted(tool_freq.items(), key=lambda x: -x[1]):
        print(f"  {tool}: {count} calls")
    print()

    # Per-test results
    print("Per-test results:")
    for r in results:
        icon = {"PASS": "OK", "WARN": "!!", "FAIL": "XX"}[r["status"]]
        tools_ok = "Y" if r["tool_analysis"].get("tool_match") else "N"
        print(f"  [{icon}] {r['name']:<35} {r['duration']:>5.1f}s  tools:{tools_ok}  {r['response_length']:>5} chars")

    # ── Save results ─────────────────────────────────────────────────────
    report = {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "backend_url": BACKEND_URL,
        "total_tests": len(results),
        "total_duration_seconds": round(total_elapsed, 1),
        "summary": {
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
            "tool_match_rate": round(tool_match_count / len(results) * 100, 1),
            "timeout_count": timeout_count,
        },
        "category_stats": category_stats,
        "tool_frequency": tool_freq,
        "results": results,
    }

    RESULTS_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDetailed results saved to: {RESULTS_FILE}")

    if fail_count > 0:
        print(f"\n{fail_count} test(s) failed. Review output above for details.")
        sys.exit(1)
    elif warn_count > 0:
        print(f"\n{warn_count} test(s) with warnings. All critical checks passed.")
    else:
        print("\nAll tests passed!")


if __name__ == "__main__":
    main()

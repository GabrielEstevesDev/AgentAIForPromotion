
"""
Second-round evaluation script — focuses on:
1. reliability regressions,
2. prospecting / client-opportunity use cases,
3. stronger RAG safety checks,
4. richer HITL business quality.

Usage:
    python backend/tests/full_eval_round2.py

Requirements:
    - Backend running on http://127.0.0.1:8001
    - httpx: pip install httpx
"""

import json
import sys
import time
import uuid
from datetime import datetime

import httpx

BACKEND_URL = "http://127.0.0.1:8001"
TIMEOUT = 120

PROMPTS = [
    # ------------------------------------------------------------------
    # A. Reliability / consistency regression tests
    # ------------------------------------------------------------------
    "What were our total sales in the last 30 days? State the exact date range used, whether cancelled orders are included, and include total revenue, order count, and average order value.",
    "Show total revenue for the last 30 days excluding cancelled orders, then compare it to the previous 30-day period and explain the difference.",
    "Show total revenue for the last 7 days and compare it to the previous 7-day period. Make sure the date ranges are explicit.",
    "Break down revenue by category for the last 30 days and include each category's share of total revenue.",
    "List the top 10 products by revenue in the last 30 days and include each product's share of total revenue.",
    "Show the lowest-stock products even if none are critical. State the threshold used and sort by stock ascending.",
    "Which products are genuinely at risk of stockout within the next 14 days based on current sales velocity? Only include products that meet that condition.",
    "Recommend replenishment actions for the next 30 days using a target of 30 days of stock cover. Include current stock, daily velocity, days of cover, suggested reorder quantity, and estimated line cost.",
    "If no products require replenishment under a 14-day stockout threshold, say so clearly and do not create a meaningless purchase order.",
    "Show me the SQL and explain exactly which filters you used to calculate last 30 days revenue, including how you handled cancelled orders.",

    # ------------------------------------------------------------------
    # B. Better business analysis / decision quality
    # ------------------------------------------------------------------
    "Analyze the last 30 days of sales and identify the 3 biggest opportunities to increase revenue. Include total revenue, order count, average order value, top categories, underperforming categories, and 3 actions tied directly to the evidence.",
    "Which categories are underperforming relative to their share of the catalog? Explain why that matters and what we should do next.",
    "Which products have strong customer ratings but low sales? Include why each one is a good candidate for promotion, bundling, or better placement.",
    "Analyze our customer base and identify the most valuable customer segments. Include segment definitions, revenue contribution, and recommended actions.",
    "Create an executive summary of business performance for the last 30 days with one chart and 3 strategic recommendations ranked by expected impact.",

    # ------------------------------------------------------------------
    # C. Charts with interpretation
    # ------------------------------------------------------------------
    "Create a chart showing revenue by category for the last 30 days and explain what the chart implies for next month's priorities.",
    "Create a chart of the top 10 products by revenue and tell me what decision we should make based on it.",
    "Visualize average order value by month for the last 12 months and explain whether AOV is improving or weakening.",
    "Create a chart showing products most at risk of stockout based on days of cover and explain which items need action first.",
    "Show the distribution of product ratings across all reviews and explain whether customer sentiment looks healthy overall.",

    # ------------------------------------------------------------------
    # D. RAG / policy safety
    # ------------------------------------------------------------------
    "What is our return policy for defective items? Answer with the policy, exceptions, and source document.",
    "Explain how bundle discounts work according to our internal guidelines. Separate binding policy from general guidance.",
    "Summarize the main recommendations from the Trends & Analytics report and prioritize the top 3 actions.",
    "What are the key rules around promo codes and bundles in our internal documents?",
    "What is our official warranty policy for electronics? If this is not clearly stated in the knowledge base, say that explicitly and do not invent one.",

    # ------------------------------------------------------------------
    # E. Web + internal relevance
    # ------------------------------------------------------------------
    "What are the latest e-commerce product bundling trends in 2025? Summarize the top 3 trends and explain how they apply to our business.",
    "What are current best practices for increasing average order value in e-commerce? Then explain which ideas are most relevant to our catalog.",
    "Research current trends in e-commerce customer retention and tell me which 2 ideas we should test first, and why.",

    # ------------------------------------------------------------------
    # F. HITL quality
    # ------------------------------------------------------------------
    "Create a 30-day promotion strategy to increase revenue based on our sales data. Include baseline revenue, top categories, target products, expected uplift range, key risks, and KPI targets.",
    "Create a promotion strategy focused on inventory clearance rather than revenue growth. Make the rationale data-driven.",
    "Create a 30-day promotion strategy with a maximum budget of $5,000 and a maximum discount of 15%.",
    "Analyze inventory levels and recommend which products we should reorder from suppliers. Include current stock, daily velocity, days of cover, suggested reorder quantity, and estimated total cost. Then prepare a draft purchase order.",
    "Create a purchase order draft for products at risk of stockout within 14 days, with a total budget cap of $1,000. If no products qualify, say so clearly instead of forcing a draft.",
    "Which products should we reorder first if we can only spend $500? Prioritize by urgency and expected business impact.",

    # ------------------------------------------------------------------
    # G. New prospecting / client-opportunity mode
    # ------------------------------------------------------------------
    "We are pitching this product to a mid-size DTC beauty brand. What AI use cases should we prioritize for them based on Aria's capabilities?",
    "For a multi-brand retailer, what workflows could be automated or copiloted with Aria? Organize the answer by team and business value.",
    "What is the best pilot project to propose to a sporting goods retailer if we want a fast, credible AI win in under 6 weeks?",
    "Turn Aria's capabilities into a client-facing opportunity map for a home & garden e-commerce prospect. Include likely pain points, recommended AI workflows, teams affected, data required, and suggested first pilot.",
    "A prospect asks: 'Why do I need this instead of dashboards plus a chatbot?' Give a concise, client-facing answer grounded in concrete workflows.",
    "Use our internal documents plus current web trends to recommend a better bundling strategy for our business, then explain how that same workflow could be sold to a future retail client.",
    "Based on Aria's current capabilities, which 5 demo scenarios are strongest for presales conversations with future clients? Rank them by credibility and business value.",
    "If you were a solutions consultant using Aria, how would you position it differently for a retailer, a DTC brand, and a marketplace operator?",

    # ------------------------------------------------------------------
    # H. Anti-hallucination / safe fallback
    # ------------------------------------------------------------------
    "What were our exact sales on March 3, 2024? If the data is not available, say so clearly.",
    "Create a purchase order for 1,000 units of our best-selling products immediately.",
    "Send a refund email to a customer for a damaged item.",
]


def _create_conversation(title: str) -> str:
    r = httpx.post(
        f"{BACKEND_URL}/api/conversations",
        json={"title": title},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["id"]


def send_prompt(prompt: str, conversation_id: str) -> str:
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "conversationId": conversation_id,
    }
    full_response = []

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
                            raise RuntimeError(f"Backend error: {err.get('detail', data_str)}")
                        except json.JSONDecodeError:
                            raise RuntimeError(f"Backend error: {data_str}")
                    if current_event == "token":
                        try:
                            parsed = json.loads(data_str)
                            token = parsed.get("token", "")
                            if token:
                                full_response.append(token)
                        except json.JSONDecodeError:
                            pass
                    current_event = ""
                    continue

    return "".join(full_response)


def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"backend/tests/full_eval_round2_results_{timestamp}.txt"

    # Check backend
    try:
        httpx.get(f"{BACKEND_URL}/docs", timeout=5)
    except httpx.ConnectError:
        print(f"ERROR: Cannot connect to backend at {BACKEND_URL}")
        print("Start the backend first.")
        sys.exit(1)

    print(f"Running {len(PROMPTS)} prompts against {BACKEND_URL}")
    print(f"Output: {output_file}")
    print("=" * 70)

    lines = []
    lines.append(f"Second-Round Evaluation Results — {datetime.now().isoformat()}")
    lines.append(f"Backend: {BACKEND_URL}")
    lines.append(f"Prompts: {len(PROMPTS)}")
    lines.append("=" * 70)
    lines.append("")

    total_start = time.time()

    for i, prompt in enumerate(PROMPTS, 1):
        print(f"[{i}/{len(PROMPTS)}] {prompt[:70]}...")
        start = time.time()

        try:
            conv_id = _create_conversation(f"eval2-{i}-{uuid.uuid4().hex[:6]}")
            response = send_prompt(prompt, conv_id)
            elapsed = time.time() - start
            print(f"  OK ({elapsed:.1f}s, {len(response)} chars)")
        except Exception as e:
            elapsed = time.time() - start
            response = f"[ERROR: {e}]"
            print(f"  ERROR ({elapsed:.1f}s): {e}")

        lines.append(f"{'─' * 70}")
        lines.append(f"PROMPT {i}: {prompt}")
        lines.append(f"Time: {elapsed:.1f}s | Length: {len(response)} chars")
        lines.append(f"{'─' * 70}")
        lines.append(response)
        lines.append("")
        lines.append("")

    total_elapsed = time.time() - total_start
    summary = f"Completed {len(PROMPTS)} prompts in {total_elapsed:.0f}s"
    print(f"\n{summary}")
    lines.append("=" * 70)
    lines.append(summary)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Results saved to {output_file}")


if __name__ == "__main__":
    main()

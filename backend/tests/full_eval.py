"""
Full evaluation script — sends structured test prompts to the running backend,
checks each response against pass/fail criteria, and saves all responses to a
timestamped text file.

Usage:
    python backend/tests/full_eval.py

Requirements:
    - Backend running on http://127.0.0.1:8001
    - httpx: pip install httpx
"""

import json
import os
import re
import sys
import time
import uuid
from datetime import datetime

import httpx

# Allow running from project root or from backend/tests/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_prompts import check_test

BACKEND_URL = "http://127.0.0.1:8001"
TIMEOUT = 120

# ─── Structured test cases ────────────────────────────────────────────────────
# Each test has a name, prompt, and pass/fail criteria (same schema as eval_prompts.py)

TESTS = [
    # ── Sales & Revenue ──
    {
        "name": "1. Sales last 30 days",
        "prompt": "What were our total sales in the last 30 days?",
        "required": ["revenue"],
        "required_any": [["30 day", "30-day", "last 30"]],
        "forbidden": [],
        "require_current_year": True,
    },
    {
        "name": "2. Orders + revenue + AOV (30d)",
        "prompt": "Show the total number of orders, total revenue, and average order value for the last 30 days.",
        "required": ["revenue", "order"],
        "required_any": [["aov", "average order value", "avg"]],
        "forbidden": [],
    },
    {
        "name": "3. Revenue by category (30d)",
        "prompt": "Which product categories generated the most revenue in the last 30 days?",
        "required": ["category", "revenue"],
        "required_any": [],
        "forbidden": [],
    },
    {
        "name": "4. Top 10 products by revenue (30d)",
        "prompt": "What are the top 10 products by revenue in the last 30 days?",
        "required": ["revenue"],
        "required_any": [],
        "forbidden": [],
    },
    {
        "name": "5. Top customers by spend",
        "prompt": "Who are our top 5 customers by total spend?",
        "required": [],
        "required_any": [["spend", "spent", "revenue"]],
        "forbidden": [],
    },
    {
        "name": "6. Revenue 30d with exact date range",
        "prompt": "Show me revenue for the last 30 days, excluding cancelled orders, and state the exact date range used.",
        "required": ["revenue"],
        "required_any": [["2026"]],
        "forbidden": [],
        "require_current_year": True,
    },
    {
        "name": "7. Revenue with/without cancelled",
        "prompt": "Show me revenue for the last 30 days, including cancelled orders, and compare it to revenue excluding cancelled orders.",
        "required": ["revenue"],
        "required_any": [["cancelled", "canceled"]],
        "forbidden": [],
    },
    {
        "name": "8. Sales last 7 days vs prior",
        "prompt": "What were our total sales in the last 7 days, and compare that to the previous 7-day period?",
        "required": ["revenue"],
        "required_any": [["7 day", "7-day", "last 7"]],
        "forbidden": [],
    },
    # ── Inventory ──
    {
        "name": "9. Low inventory products",
        "prompt": "Show me the lowest inventory products, even if none are critically low. Include the threshold you used.",
        "required": ["stock"],
        "required_any": [["threshold", "below", "level"]],
        "forbidden": [],
    },
    {
        "name": "10. Stockout risk 14 days",
        "prompt": "Which products are at risk of stockout in the next 14 days based on current sales velocity?",
        "required": [],
        "required_any": [["velocity", "days of cover", "days of stock"]],
        "forbidden": ["999"],
    },
    # ── Complex Analysis ──
    {
        "name": "11. 30d sales opportunities",
        "prompt": "Analyze the last 30 days of sales and identify the 3 biggest opportunities to increase revenue. Include total revenue, order count, average order value, top categories, underperforming categories, and 3 specific actions tied to the data.",
        "required": ["revenue"],
        "required_any": [["recommend", "action", "opportunity"]],
        "forbidden": [],
    },
    {
        "name": "12. High rated low sales",
        "prompt": "Which products have strong customer ratings but low sales? Include why each product is a good candidate for promotion or testing.",
        "required": ["rating"],
        "required_any": [["revenue", "sales", "units"]],
        "forbidden": [],
    },
    {
        "name": "13. Customer segments",
        "prompt": "Analyze our customer base and identify the most valuable customer segments. Include segment definitions, revenue contribution, and recommended actions.",
        "required": ["segment"],
        "required_any": [["revenue", "spend"]],
        "forbidden": [],
    },
    {
        "name": "14. Underperforming categories",
        "prompt": "Which categories are underperforming relative to their share of the catalog?",
        "required": ["category"],
        "required_any": [],
        "forbidden": [],
    },
    # ── Charts ──
    {
        "name": "15. Chart: revenue by category",
        "prompt": "Create a chart showing revenue by category for the last 30 days and explain what the chart implies.",
        "required": ["/api/charts/"],
        "required_any": [],
        "forbidden": [],
    },
    {
        "name": "16. Chart: top products",
        "prompt": "Create a chart of the top 10 products by revenue and tell me what action we should take based on it.",
        "required": ["/api/charts/"],
        "required_any": [],
        "forbidden": [],
    },
    {
        "name": "17. Chart: AOV by month",
        "prompt": "Visualize average order value by month for the last 12 months.",
        "required": ["/api/charts/"],
        "required_any": [],
        "forbidden": [],
    },
    {
        "name": "18. Chart: stockout risk",
        "prompt": "Create a chart showing which products are most at risk of stockout based on days of cover.",
        "required": ["/api/charts/"],
        "required_any": [],
        "forbidden": [],
    },
    {
        "name": "19. Rating distribution",
        "prompt": "Show me the distribution of product ratings across all reviews, and explain whether customer sentiment looks healthy overall.",
        "required": ["rating"],
        "required_any": [],
        "forbidden": [],
    },
    # ── RAG ──
    {
        "name": "20. Return policy (RAG)",
        "prompt": "What is our return policy for defective items? Answer with the policy, exceptions, and source.",
        "required": ["policy"],
        "required_any": [["source", "policy:"]],
        "forbidden": [],
    },
    {
        "name": "21. Bundle discounts (RAG)",
        "prompt": "Explain how bundle discounts work according to our internal guidelines. Separate binding policy from general guidance.",
        "required": [],
        "required_any": [["bundle", "discount"]],
        "forbidden": [],
    },
    {
        "name": "22. Trends report (RAG)",
        "prompt": "Summarize the main recommendations from the Trends & Analytics report and prioritize the top 3 actions.",
        "required": [],
        "required_any": [["recommend", "action", "trend"]],
        "forbidden": [],
    },
    {
        "name": "23. Promo rules (RAG)",
        "prompt": "What are the key rules around promo codes and bundles in our internal documents?",
        "required": [],
        "required_any": [["promo", "bundle", "discount", "code"]],
        "forbidden": [],
    },
    # ── Web Search ──
    {
        "name": "24. Bundling trends (WEB)",
        "prompt": "What are the latest e-commerce product bundling trends in 2025? Summarize the top 3 trends and explain how they apply to our business.",
        "required": [],
        "required_any": [["relevance", "business", "our catalog", "our strategy", "our product"]],
        "forbidden": [],
    },
    {
        "name": "25. AOV best practices (WEB)",
        "prompt": "What are current best practices for increasing average order value in e-commerce? Then explain which of those ideas are most relevant to our catalog.",
        "required": [],
        "required_any": [["aov", "average order value", "order value"]],
        "forbidden": [],
    },
    {
        "name": "26. Customer retention (WEB)",
        "prompt": "Research current trends in customer retention for e-commerce and tell me which 2 ideas we should test first.",
        "required": [],
        "required_any": [["retention", "loyalty"]],
        "forbidden": [],
    },
    # ── HITL: Promotions ──
    {
        "name": "27. Promotion strategy (HITL)",
        "prompt": "Create a 30-day promotion strategy to increase revenue based on our sales data. Include baseline revenue, top categories, target products, expected uplift range, key risks, and KPI targets.",
        "required": ["HITL_REQUEST"],
        "required_any": [["revenue"]],
        "forbidden": [],
    },
    {
        "name": "28. Inventory clearance promo (HITL)",
        "prompt": "Create a promotion strategy focused on inventory clearance rather than revenue growth.",
        "required": ["HITL_REQUEST"],
        "required_any": [],
        "forbidden": [],
    },
    {
        "name": "29. Constrained promo (HITL)",
        "prompt": "Create a 30-day promotion strategy with a maximum budget of $5,000 and a maximum discount of 15%.",
        "required": ["HITL_REQUEST"],
        "required_any": [],
        "forbidden": [],
    },
    {
        "name": "30. Underperforming categories promo (HITL)",
        "prompt": "Create a promotion strategy, but this time prioritize underperforming categories instead of top-performing ones.",
        "required": ["HITL_REQUEST"],
        "required_any": [],
        "forbidden": [],
    },
    # ── HITL: Purchase Orders ──
    {
        "name": "31. Reorder recommendation + PO (HITL)",
        "prompt": "Analyze inventory levels and recommend which products we should reorder from suppliers. Include current stock, daily velocity, days of cover, suggested reorder quantity, and estimated total cost. Then prepare a draft purchase order.",
        "required": [],
        "required_any": [["HITL_REQUEST", "sufficient stock", "no reorder", "no replenishment"]],
        "forbidden": [],
    },
    {
        "name": "32. Stockout PO with budget cap (HITL)",
        "prompt": "Create a purchase order draft for products at risk of stockout within 14 days, with a total budget cap of $1,000.",
        "required": [],
        "required_any": [["HITL_REQUEST", "sufficient stock", "no reorder", "no items"]],
        "forbidden": [],
    },
    {
        "name": "33. 30-day replenishment PO (HITL)",
        "prompt": "Recommend replenishment actions for the next 30 days using a target of 30 days of stock cover. Then prepare a draft purchase order.",
        "required": [],
        "required_any": [["HITL_REQUEST", "sufficient stock", "no reorder", "no replenishment"]],
        "forbidden": [],
    },
    {
        "name": "34. Prioritized reorder $500 budget",
        "prompt": "Which products should we reorder first if we can only spend $500? Prioritize by urgency and expected business impact.",
        "required": [],
        "required_any": [["velocity", "stock", "days", "sufficient"]],
        "forbidden": [],
    },
    # ── Multi-tool ──
    {
        "name": "35. 30d analysis + chart + recommendations",
        "prompt": "Analyze the last 30 days of sales, create one chart, and finish with 3 concrete recommendations ranked by expected impact.",
        "required": ["revenue"],
        "required_any": [["recommend", "action"]],
        "forbidden": [],
    },
    {
        "name": "36. RAG + WEB bundling strategy",
        "prompt": "Use our internal documents plus current web trends to recommend a better bundling strategy for our business.",
        "required": [],
        "required_any": [["bundle", "discount"]],
        "forbidden": [],
    },
    {
        "name": "37. Category comparison",
        "prompt": "Compare our strongest product category with one underperforming category and explain where we should focus next month's effort.",
        "required": ["category"],
        "required_any": [],
        "forbidden": [],
    },
    {
        "name": "38. Executive summary 30d",
        "prompt": "Create an executive summary of business performance for the last 30 days with one chart and 3 strategic recommendations.",
        "required": ["revenue"],
        "required_any": [["recommend", "action", "strategy"]],
        "forbidden": [],
        "require_current_year": True,
    },
    # ── Edge Cases ──
    {
        "name": "39. Specific date query",
        "prompt": "What were our exact sales on March 3, 2024? If the data is not available, say so clearly.",
        "required": [],
        "required_any": [],
        "forbidden": [],
    },
    {
        "name": "40. PO without approval (should block)",
        "prompt": "Create a purchase order for 1,000 units of our best-selling products immediately.",
        "required": [],
        "required_any": [["HITL", "approval", "approve"]],
        "forbidden": [],
    },
    {
        "name": "41. Refund email (HITL)",
        "prompt": "Send a refund email to a customer for a damaged item.",
        "required": ["HITL_REQUEST"],
        "required_any": [],
        "forbidden": [],
    },
    {
        "name": "42. Warranty policy (RAG honesty)",
        "prompt": "What is our official warranty policy for electronics? If this is not in the knowledge base, do not invent it.",
        "required": [],
        "required_any": [["does not", "no official", "no explicit", "not a guarantee", "not a platform guarantee", "check with", "manufacturer", "industry norm", "not contain"]],
        "forbidden": [],
        "forbidden_patterns": [r"all electronics come with.*1 year", r"minimum warranty of 1 year"],
    },
    {
        "name": "43. SQL transparency",
        "prompt": "Show me the SQL and explain exactly which filters you used to calculate last 30 days revenue.",
        "required": [],
        "required_any": [["cancelled", "canceled", "status"]],
        "forbidden": [],
    },
    # ── Client Discovery / Prospecting (8 new) ──
    {
        "name": "44. Top 5 AI use cases for clients",
        "prompt": "What are the top 5 AI use cases we could demonstrate to a mid-size e-commerce client?",
        "required": [],
        "required_any": [["use case", "workflow", "capability"], ["pilot", "demo", "proof", "recommend"]],
        "forbidden": [],
    },
    {
        "name": "45. Fashion e-commerce inventory demo",
        "prompt": "A potential client in fashion e-commerce wants to see how AI helps with inventory. Run a demo analysis.",
        "required": [],
        "required_any": [["stock", "inventory", "velocity"]],
        "forbidden": [],
    },
    {
        "name": "46. B2B industrial supplies",
        "prompt": "How would our AI assistant help a B2B industrial supplies company? Demonstrate with our data.",
        "required": [],
        "required_any": [["workflow", "use case", "capability", "demo"]],
        "forbidden": [],
    },
    {
        "name": "47. Teams that benefit most",
        "prompt": "Which teams in a typical e-commerce company would benefit most from an AI copilot like Aria?",
        "required": [],
        "required_any": [["merchandising", "ops", "customer", "finance", "marketing", "executive", "team"]],
        "forbidden": [],
    },
    {
        "name": "48. 30-day pilot plan",
        "prompt": "Design a 30-day pilot plan for a new client who wants to test AI-assisted merchandising.",
        "required": [],
        "required_any": [["pilot", "30 day", "30-day"], ["KPI", "metric", "success", "milestone"]],
        "forbidden": [],
    },
    {
        "name": "49. Refund workflow mapping",
        "prompt": "Map out how a customer service team handles refunds today vs. with our AI assistant.",
        "required": [],
        "required_any": [["time", "manual", "step", "workflow"]],
        "forbidden": [],
    },
    {
        "name": "50. ROI case",
        "prompt": "Build an ROI case for why a $5M/year e-commerce company should invest in this AI copilot.",
        "required": [],
        "required_any": [["time", "hours", "saved", "reclaim"], ["revenue", "cost", "ROI", "return", "impact"]],
        "forbidden": [],
    },
    {
        "name": "51. 3-point demo script",
        "prompt": "I'm presenting to a potential client in 10 minutes. Give me a 3-point demo script.",
        "required": [],
        "required_any": [["demo", "script", "point", "show"]],
        "forbidden": [],
    },
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
    output_file = f"backend/tests/full_eval_results_{timestamp}.txt"

    # Check backend
    try:
        httpx.get(f"{BACKEND_URL}/docs", timeout=5)
    except httpx.ConnectError:
        print(f"ERROR: Cannot connect to backend at {BACKEND_URL}")
        print("Start the backend first.")
        sys.exit(1)

    print(f"Running {len(TESTS)} tests against {BACKEND_URL}")
    print(f"Output: {output_file}")
    print("=" * 70)

    lines = []
    lines.append(f"Full Evaluation Results — {datetime.now().isoformat()}")
    lines.append(f"Backend: {BACKEND_URL}")
    lines.append(f"Tests: {len(TESTS)}")
    lines.append("=" * 70)
    lines.append("")

    results = []
    total_start = time.time()

    for i, test in enumerate(TESTS, 1):
        print(f"[{i}/{len(TESTS)}] {test['name']}")
        print(f"  Prompt: {test['prompt'][:70]}...")
        start = time.time()

        try:
            conv_id = _create_conversation(f"eval-{i}-{uuid.uuid4().hex[:6]}")
            response = send_prompt(test["prompt"], conv_id)
            elapsed = time.time() - start
            passed, failures = check_test(test, response)

            status = "PASS" if passed else "FAIL"
            print(f"  {status} ({elapsed:.1f}s, {len(response)} chars)")

            if not passed:
                for f in failures:
                    print(f"    - {f}")

            results.append({
                "name": test["name"],
                "passed": passed,
                "elapsed": elapsed,
                "failures": failures,
                "response_length": len(response),
            })

        except Exception as e:
            elapsed = time.time() - start
            response = f"[ERROR: {e}]"
            print(f"  ERROR ({elapsed:.1f}s): {e}")
            results.append({
                "name": test["name"],
                "passed": False,
                "elapsed": elapsed,
                "failures": [f"Exception: {e}"],
                "response_length": 0,
            })

        lines.append(f"{'─' * 70}")
        lines.append(f"TEST {i}: {test['name']}")
        lines.append(f"Prompt: {test['prompt']}")
        lines.append(f"Time: {elapsed:.1f}s | Length: {len(response)} chars | {'PASS' if results[-1]['passed'] else 'FAIL'}")
        if results[-1]["failures"]:
            lines.append(f"Failures: {'; '.join(results[-1]['failures'])}")
        lines.append(f"{'─' * 70}")
        lines.append(response)
        lines.append("")
        lines.append("")

        print()

    # Summary
    total_elapsed = time.time() - total_start
    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)

    print("=" * 70)
    print(f"RESULTS: {passed_count}/{total_count} passed ({total_elapsed:.0f}s total)")
    print("=" * 70)

    for r in results:
        icon = "PASS" if r["passed"] else "FAIL"
        print(f"  {icon}  {r['name']} ({r['elapsed']:.1f}s)")

    lines.append("=" * 70)
    lines.append(f"RESULTS: {passed_count}/{total_count} passed ({total_elapsed:.0f}s total)")
    lines.append("=" * 70)
    for r in results:
        icon = "PASS" if r["passed"] else "FAIL"
        lines.append(f"  {icon}  {r['name']} ({r['elapsed']:.1f}s)")
        if r["failures"]:
            for f in r["failures"]:
                lines.append(f"    - {f}")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nResults saved to {output_file}")

    if passed_count < total_count:
        print(f"\n{total_count - passed_count} test(s) failed. Review output above for details.")
        sys.exit(1)
    else:
        print("\nAll tests passed!")


if __name__ == "__main__":
    main()

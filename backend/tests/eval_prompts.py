"""
Evaluation harness for Aria agent responses.

Sends test prompts to the running backend via POST /api/chat (SSE)
and checks each response against required/forbidden string criteria,
length limits, and structural checks.

Usage:
    python backend/tests/eval_prompts.py

Requirements:
    - Backend must be running on http://127.0.0.1:8001
    - httpx: pip install httpx
"""

import json
import re
import sys
import time
import uuid

# Fix Windows console encoding for Unicode characters
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx

BACKEND_URL = "http://127.0.0.1:8001"
TIMEOUT = 180  # seconds per prompt

# ─── Test cases ──────────────────────────────────────────────────────────────

TESTS = [
    {
        "name": "1. Sales last 30 days",
        "prompt": "What were our total sales in the last 30 days?",
        "required": ["revenue", "order"],
        "required_any": [["takeaway", "summary", "change", "period"]],
        "forbidden": [],
        "max_response_length": 2000,
    },
    {
        "name": "2. Revenue by category",
        "prompt": "Show me revenue by category with percentage share",
        "required": ["revenue", "category"],
        "required_any": [["%", "share", "percent"]],
        "forbidden": [],
        "max_response_length": 3000,
    },
    {
        "name": "3. Stockout risk",
        "prompt": "Which products are at risk of stockout? Show days of stock cover.",
        "required": ["stock"],
        "required_any": [["days", "cover", "velocity", "risk"], ["recommend", "action", "reorder", "takeaway"]],
        "forbidden": [],
        "max_response_length": 3000,
    },
    {
        "name": "4. High-rated low-sales",
        "prompt": "What products have high ratings but low sales?",
        "required": ["rating"],
        "required_any": [["revenue", "sales", "units sold", "sold"]],
        "forbidden": [],
        "max_response_length": 3000,
    },
    {
        "name": "5. Return policy (RAG)",
        "prompt": "What is our return policy?",
        "required": ["policy"],
        "required_any": [["source", "policy:"]],
        "forbidden": [],
        "max_response_length": 1500,
    },
    {
        "name": "6. Web trends",
        "prompt": "What are the latest e-commerce trends for 2025? Connect findings to our business.",
        "required": [],
        "required_any": [["relevance", "business", "our catalog", "our strategy", "our product"]],
        "forbidden": [],
        "max_response_length": 2500,
    },
    {
        "name": "7. Chart: revenue by category",
        "prompt": "Show me a chart of revenue by category",
        "required": ["/api/charts/"],
        "required_any": [],
        "forbidden": [],
        "max_response_length": 2500,
    },
    {
        "name": "8. Promotion strategy (HITL)",
        "prompt": "Create a 30-day promotion strategy to boost revenue",
        "required": ["HITL_REQUEST", "revenue", "risk_tags"],
        "required_any": [],
        "forbidden": [],
        "max_response_length": 5000,
    },
    {
        "name": "9. Purchase order (HITL)",
        "prompt": "We need to restock low inventory items. Create a purchase order.",
        "required": [],
        "required_any": [["HITL_REQUEST", "sufficient stock", "no reorder", "no replenishment"]],
        "forbidden": [],
        "max_response_length": 5000,
    },
    {
        "name": "10. Customer segments",
        "prompt": "Analyze our customer segments",
        "required": ["segment"],
        "required_any": [["revenue", "spend", "vip"]],
        "forbidden": [],
        "max_response_length": 3000,
    },
    {
        "name": "11. Revenue consistency check",
        "prompt": "Show total revenue for the last 30 days and break it down by category.",
        "required": ["revenue", "category"],
        "required_any": [["30 day", "30-day", "last 30"]],
        "forbidden": [],
        "require_current_year": True,
        "max_response_length": 3500,
    },
    {
        "name": "12. 7-day sales uses correct window",
        "prompt": "What were our total sales in the last 7 days?",
        "required": ["revenue"],
        "required_any": [["7 day", "7-day", "last 7"]],
        "forbidden": ["30 days"],
        "max_response_length": 1500,
    },
    {
        "name": "13. Stockout risk excludes safe products",
        "prompt": "Which products are at risk of stockout within 14 days based on velocity?",
        "required": [],
        "required_any": [["velocity", "days of cover", "days of stock"]],
        "forbidden": ["999"],
        "max_response_length": 3000,
    },
    {
        "name": "14. PO draft has non-zero quantities",
        "prompt": "We need to restock. Create a purchase order for products that need replenishment.",
        "required": [],
        "required_any": [["HITL_REQUEST", "no reorder", "sufficient stock", "no replenishment"]],
        "forbidden": [],
        "max_response_length": 5000,
    },
    {
        "name": "15. RAG does not invent warranty",
        "prompt": "What is our official warranty policy for electronics? Only state what is in our knowledge base.",
        "required": [],
        "required_any": [["does not", "no official", "no explicit", "not a guarantee", "not a platform guarantee", "check with", "manufacturer", "industry norm"]],
        "forbidden": [],
        "forbidden_patterns": [r"all electronics come with.*1 year", r"minimum warranty of 1 year"],
        "max_response_length": 1500,
    },
    {
        "name": "16. Prospect: use case identification",
        "prompt": "What are the top 5 AI use cases we could demo to a potential e-commerce client?",
        "required": [],
        "required_any": [["use case", "workflow", "capability"], ["pilot", "demo", "proof", "recommend"]],
        "forbidden": [],
        "max_response_length": 4000,
    },
    {
        "name": "17. Prospect: ROI narrative",
        "prompt": "Build an ROI case for an e-commerce company considering our AI copilot.",
        "required": [],
        "required_any": [["time", "hours", "saved", "reclaim", "efficiency", "faster", "automat"], ["revenue", "cost", "ROI", "return", "impact", "$"]],
        "forbidden": [],
        "max_response_length": 4000,
    },
    # ── New tests: brevity, completion, prospecting, charts ─────────────────
    {
        "name": "18. Factual brevity — top 5 products",
        "prompt": "What are our top 5 products by revenue?",
        "required": ["revenue"],
        "required_any": [],
        "forbidden": [],
        "max_response_length": 1500,
    },
    {
        "name": "19. Promotion strategy completes (no timeout)",
        "prompt": "Create a 30-day promotion strategy to boost revenue based on our sales data",
        "required": ["HITL_REQUEST"],
        "required_any": [],
        "forbidden": ["took too long", "was stopped"],
        "max_response_length": 5000,
        "require_completion": True,
    },
    {
        "name": "20. Prospecting — opportunity scan",
        "prompt": "What AI use cases would you recommend for a mid-size e-commerce company? Show me a quick opportunity scan with live data.",
        "required": [],
        "required_any": [["opportunity", "use case", "workflow"], ["$", "revenue", "orders"]],
        "forbidden": [],
        "max_response_length": 4000,
    },
    {
        "name": "21. Chart insight is concise",
        "prompt": "Show me a chart of revenue by category",
        "required": ["/api/charts/"],
        "required_any": [],
        "forbidden": [],
        "max_response_length": 2000,
    },
    {
        "name": "22. PO draft has grand total",
        "prompt": "Create a purchase order for items at stockout risk",
        "required": [],
        "required_any": [["HITL_REQUEST", "no reorder", "sufficient stock", "no replenishment"]],
        "forbidden": [],
        "max_response_length": 5000,
    },
    {
        "name": "23. Simple question is short",
        "prompt": "How many customers do we have?",
        "required": [],
        "required_any": [["customer"]],
        "forbidden": [],
        "max_response_length": 800,
    },
]


def _create_conversation() -> str:
    """Create a new conversation via the API and return its ID."""
    r = httpx.post(
        f"{BACKEND_URL}/api/conversations",
        json={"title": f"eval-{uuid.uuid4().hex[:8]}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["id"]


def send_prompt(prompt: str) -> tuple[str, bool]:
    """Send a prompt to the backend SSE endpoint and collect the full response.

    Returns (response_text, timed_out).
    """
    conversation_id = _create_conversation()
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "conversationId": conversation_id,
    }

    full_response = []
    timed_out = False

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
                    # SSE format: "event: <name>" then "data: <json>"
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
                                raise RuntimeError(f"Backend error: {detail}")
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

    except httpx.ReadTimeout:
        timed_out = True

    return "".join(full_response), timed_out


def check_test(test: dict, response: str, timed_out: bool) -> tuple[str, list[str]]:
    """Check response against criteria. Returns (status, failures).

    Status is one of: "PASS", "WARN", "FAIL".
    """
    failures = []
    warnings = []
    response_lower = response.lower()

    # Timeout check
    if timed_out:
        failures.append("TIMEOUT — response did not complete")
        if test.get("require_completion"):
            failures.append("COMPLETION REQUIRED but timed out")

    # Timeout indicator in response
    if "took too long" in response_lower or "was stopped" in response_lower:
        failures.append("Response contains timeout warning text")

    for req in test.get("required", []):
        if req.lower() not in response_lower:
            failures.append(f"MISSING required: '{req}'")

    # required_any: at least one from each group must be present
    for group in test.get("required_any", []):
        if group and not any(alt.lower() in response_lower for alt in group):
            failures.append(f"MISSING one of: {group}")

    for forbidden in test.get("forbidden", []):
        if forbidden.lower() in response_lower:
            failures.append(f"FOUND forbidden: '{forbidden}'")

    # Non-zero table check
    if test.get("require_nonzero_table"):
        table_lines = [l for l in response.split("\n") if "|" in l and "---" not in l]
        if table_lines:
            data_lines = table_lines[1:]  # skip header
            has_nonzero = any(
                re.search(r'\$[1-9]', line) for line in data_lines
            )
            if not has_nonzero:
                failures.append("TABLE contains all zeros — no meaningful data")

    # Date year check
    if test.get("require_current_year"):
        if "2026" not in response:
            failures.append("Response does not mention 2026 (possible date hallucination)")

    # Forbidden exact patterns (for RAG accuracy)
    for pattern in test.get("forbidden_patterns", []):
        if re.search(pattern, response, re.IGNORECASE):
            failures.append(f"FOUND forbidden pattern: '{pattern}'")

    # Length ceiling check (warning, not failure)
    max_len = test.get("max_response_length")
    if max_len and len(response) > max_len:
        warnings.append(f"LENGTH: {len(response)} > {max_len} chars")

    # Determine status
    if failures:
        return "FAIL", failures + warnings
    elif warnings:
        return "WARN", warnings
    else:
        return "PASS", []


def main():
    print("=" * 70)
    print("Aria Agent Evaluation Harness")
    print(f"Backend: {BACKEND_URL}")
    print("=" * 70)
    print()

    # Check backend is running
    try:
        r = httpx.get(f"{BACKEND_URL}/docs", timeout=5)
    except httpx.ConnectError:
        print(f"ERROR: Cannot connect to backend at {BACKEND_URL}")
        print("Start the backend first:")
        print('  "agent/.venv/Scripts/uvicorn.exe" backend.main:app --host 127.0.0.1 --port 8001')
        sys.exit(1)

    results = []
    total_start = time.time()
    timeout_count = 0

    for i, test in enumerate(TESTS):
        print(f"[{i+1}/{len(TESTS)}] {test['name']}")
        print(f"  Prompt: {test['prompt'][:60]}...")
        start = time.time()

        try:
            response, timed_out = send_prompt(test["prompt"])
            elapsed = time.time() - start
            status, issues = check_test(test, response, timed_out)

            if timed_out:
                timeout_count += 1

            print(f"  {status} ({elapsed:.1f}s, {len(response)} chars)")

            if issues:
                for f in issues:
                    print(f"    - {f}")
                # Show first 500 chars of response for debugging
                if status == "FAIL":
                    print(f"  Response preview: {response[:500]}...")

            results.append({
                "name": test["name"],
                "status": status,
                "elapsed": elapsed,
                "issues": issues,
                "response_length": len(response),
                "timed_out": timed_out,
            })

        except Exception as e:
            elapsed = time.time() - start
            print(f"  FAIL ({elapsed:.1f}s): {e}")
            results.append({
                "name": test["name"],
                "status": "FAIL",
                "elapsed": elapsed,
                "issues": [f"Exception: {e}"],
                "response_length": 0,
                "timed_out": False,
            })

        print()

    # Summary
    total_elapsed = time.time() - total_start
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    warn_count = sum(1 for r in results if r["status"] == "WARN")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    total_count = len(results)

    print("=" * 70)
    print(f"RESULTS: {pass_count} PASS / {warn_count} WARN / {fail_count} FAIL  ({total_count} total, {total_elapsed:.0f}s)")
    if timeout_count:
        print(f"TIMEOUTS: {timeout_count}")
    print("=" * 70)

    for r in results:
        icon = r["status"]
        extra = ""
        if r.get("timed_out"):
            extra = " [TIMEOUT]"
        print(f"  {icon:4s}  {r['name']} ({r['elapsed']:.1f}s, {r['response_length']} chars){extra}")

    if fail_count > 0:
        print(f"\n{fail_count} test(s) failed. Review output above for details.")
        sys.exit(1)
    elif warn_count > 0:
        print(f"\n{warn_count} test(s) with warnings. All critical checks passed.")
    else:
        print("\nAll tests passed!")


if __name__ == "__main__":
    main()

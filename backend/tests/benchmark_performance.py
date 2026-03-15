"""
Performance benchmark for the Aria agent.

Measures granular timing metrics via backend-emitted PERF SSE events:
  - Mode classification time
  - Request -> first LLM call
  - LLM thinking before tool call
  - Per-tool execution durations
  - Per-LLM-call durations
  - TTFT (time to first text token)
  - Total tool vs LLM time breakdown
  - Total graph and request duration

Usage:
    python backend/tests/benchmark_performance.py

Requirements:
    - Backend must be running on http://127.0.0.1:8001
    - httpx: pip install httpx
"""

import json
import sys
import time
import uuid
from dataclasses import dataclass, field

# Fix Windows console encoding for Unicode characters
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx

BACKEND_URL = "http://127.0.0.1:8001"
TIMEOUT = 120  # seconds per prompt (matches project's 90s agent timeout + buffer)
RESULTS_FILE = "backend/tests/benchmark_results.json"

# ─── Test scenarios ──────────────────────────────────────────────────────────

SCENARIOS = [
    {
        "id": 1,
        "name": "Baseline (no tools)",
        "prompt": "Hello, who are you and what can you do?",
        "expected_tools": [],
        "category": "baseline",
    },
    {
        "id": 2,
        "name": "SQL Library",
        "prompt": "What is our total revenue for this year?",
        "expected_tools": ["query_library"],
        "category": "sql",
    },
    {
        "id": 3,
        "name": "Raw SQL",
        "prompt": "List the top 5 customers who haven't placed an order in the last 6 months.",
        "expected_tools": ["sql_query"],
        "category": "sql",
    },
    {
        "id": 4,
        "name": "RAG",
        "prompt": "What is our return policy for opened electronics?",
        "expected_tools": ["rag_search"],
        "category": "rag",
    },
    {
        "id": 5,
        "name": "Web Search",
        "prompt": "What are the current trending tech gadgets in March 2026?",
        "expected_tools": ["web_search"],
        "category": "web",
    },
    {
        "id": 6,
        "name": "Python/Chart",
        "prompt": "Generate a bar chart of our sales by category.",
        "expected_tools": ["python_executor"],
        "category": "chart",
    },
    {
        "id": 7,
        "name": "Multi-Tool (SQL + Web)",
        "prompt": "Analyze our inventory levels and search the web for supplier news for our top 3 products.",
        "expected_tools": ["sql_query", "web_search"],
        "category": "multi",
    },
    {
        "id": 8,
        "name": "Multi-Tool (SQL + RAG)",
        "prompt": "Compare our actual sales data with the trends mentioned in our 'Trends and Analytics' document.",
        "expected_tools": ["sql_query", "rag_search"],
        "category": "multi",
    },
    {
        "id": 9,
        "name": "HITL Flow",
        "prompt": "Draft a promotion strategy for low-stock items and prepare it for my approval.",
        "expected_tools": ["query_library", "sql_query"],
        "category": "hitl",
    },
    {
        "id": 10,
        "name": "Complex (SQL + Python + HITL)",
        "prompt": "Find our 3 worst-rated products, analyze their review sentiment, and suggest a replenishment strategy including a draft PO.",
        "expected_tools": ["sql_query", "python_executor"],
        "category": "complex",
    },
]


# ─── Data classes ────────────────────────────────────────────────────────────

@dataclass
class PerfEvent:
    """A single perf timing event from the backend."""
    name: str
    duration: float
    extra: dict = field(default_factory=dict)

    def __str__(self):
        extra_str = ""
        if self.extra:
            parts = [f"{k}={v}" for k, v in self.extra.items()]
            extra_str = f" ({', '.join(parts)})"
        return f"{self.name}: {self.duration:.3f}s{extra_str}"


@dataclass
class BenchmarkResult:
    """Performance metrics for a single scenario."""
    scenario_id: int
    scenario_name: str
    category: str

    # Client-side timing
    client_ttft: float = 0.0         # Client-measured time to first token (seconds)
    client_tps: float = 0.0          # Client-measured tokens per second
    client_duration: float = 0.0     # Client-measured full request-response time (seconds)
    total_tokens: int = 0            # Total text token chunks received
    response_length: int = 0         # Total response length in characters

    # Backend perf events (from SSE 'perf' events)
    perf_events: list = field(default_factory=list)  # list[PerfEvent]

    # Extracted key metrics from perf events (filled after run)
    backend_ttft: float = 0.0        # Backend-measured TTFT
    fastapi_ttft: float = 0.0        # FastAPI-measured TTFT
    first_llm_call: float = 0.0      # Time to first LLM call
    llm_thinking: float = 0.0        # LLM thinking before first tool call
    total_tool_time: float = 0.0     # Sum of all tool execution time
    estimated_llm_time: float = 0.0  # Estimated total LLM time
    total_graph_duration: float = 0.0  # Total graph execution time
    total_request_duration: float = 0.0  # Total request duration (backend)
    tool_calls: list = field(default_factory=list)  # [{name, duration}]
    llm_calls: list = field(default_factory=list)   # [{name, duration}]

    success: bool = False
    timed_out: bool = False
    error: str = ""


# ─── SSE stream consumer with perf capture ──────────────────────────────────

def _create_conversation() -> str:
    """Create a new conversation and return its ID."""
    r = httpx.post(
        f"{BACKEND_URL}/api/conversations",
        json={"title": f"bench-{uuid.uuid4().hex[:8]}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["id"]


def run_scenario(scenario: dict) -> BenchmarkResult:
    """Run a single benchmark scenario and collect timing + perf metrics."""
    result = BenchmarkResult(
        scenario_id=scenario["id"],
        scenario_name=scenario["name"],
        category=scenario["category"],
    )

    conversation_id = _create_conversation()
    payload = {
        "messages": [{"role": "user", "content": scenario["prompt"]}],
        "conversationId": conversation_id,
    }

    tokens: list[str] = []
    first_token_time: float = 0.0
    request_start = time.perf_counter()

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
                            result.success = True
                            break

                        if current_event == "error":
                            try:
                                err = json.loads(data_str)
                                result.error = err.get("detail", data_str)
                            except json.JSONDecodeError:
                                result.error = data_str
                            break

                        if current_event == "perf":
                            try:
                                perf_data = json.loads(data_str)
                                name = perf_data.pop("name", "unknown")
                                duration = perf_data.pop("duration", 0.0)
                                result.perf_events.append(
                                    PerfEvent(name=name, duration=duration, extra=perf_data)
                                )
                            except json.JSONDecodeError:
                                pass

                        elif current_event == "token":
                            try:
                                parsed = json.loads(data_str)
                                token = parsed.get("token", "")
                                if token:
                                    if not first_token_time:
                                        first_token_time = time.perf_counter()
                                    tokens.append(token)
                            except json.JSONDecodeError:
                                pass

                        current_event = ""
                        continue

    except httpx.ReadTimeout:
        result.timed_out = True
        result.error = "HTTP read timeout"
    except Exception as exc:
        result.error = str(exc)

    request_end = time.perf_counter()

    # ── Client-side metrics ──
    result.client_duration = round(request_end - request_start, 3)
    full_response = "".join(tokens)
    result.response_length = len(full_response)
    result.total_tokens = len(tokens)

    if first_token_time:
        result.client_ttft = round(first_token_time - request_start, 3)
    else:
        result.client_ttft = result.client_duration

    streaming_duration = result.client_duration - result.client_ttft
    if streaming_duration > 0 and result.total_tokens > 0:
        result.client_tps = round(result.total_tokens / streaming_duration, 1)

    # Check for timeout warning in response
    if "took too long" in full_response.lower() or "was stopped" in full_response.lower():
        result.timed_out = True
        if not result.error:
            result.error = "Agent timeout (90s limit)"

    if not result.success and result.total_tokens > 0 and not result.error:
        result.success = True

    # ── Extract key metrics from perf events ──
    for pe in result.perf_events:
        name_lower = pe.name.lower()

        if pe.name == "TTFT (Graph)":
            result.backend_ttft = pe.duration
        elif pe.name == "FastAPI TTFT":
            result.fastapi_ttft = pe.duration
        elif "first llm call" in name_lower:
            result.first_llm_call = pe.duration
        elif "thinking before tool" in name_lower:
            result.llm_thinking = pe.duration
        elif pe.name == "Total Tool Execution":
            result.total_tool_time = pe.duration
        elif pe.name == "Estimated LLM Time":
            result.estimated_llm_time = pe.duration
        elif pe.name == "Total Graph Duration":
            result.total_graph_duration = pe.duration
        elif pe.name == "Total Request Duration":
            result.total_request_duration = pe.duration
        elif name_lower.startswith("tool:"):
            result.tool_calls.append({"name": pe.name[6:], "duration": pe.duration})
        elif name_lower.startswith("llm call"):
            result.llm_calls.append({"name": pe.name, "duration": pe.duration})

    return result


# ─── Output formatting ──────────────────────────────────────────────────────

# ANSI colors
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _bar(value: float, max_val: float, width: int = 30) -> str:
    """Render a simple horizontal bar."""
    if max_val <= 0:
        return ""
    filled = int(min(value / max_val, 1.0) * width)
    return f"{'|' * filled}{'.' * (width - filled)}"


def print_scenario_detail(result: BenchmarkResult) -> None:
    """Print detailed perf breakdown for a single scenario."""
    status = f"{_GREEN}OK{_RESET}" if result.success else (
        f"{_RED}TIMEOUT{_RESET}" if result.timed_out else f"{_RED}ERROR{_RESET}"
    )

    print(f"\n  {_BOLD}#{result.scenario_id} {result.scenario_name}{_RESET}  [{status}]")

    if result.error:
        print(f"  {_RED}Error: {result.error[:100]}{_RESET}")

    # Waterfall-style timing breakdown
    if result.perf_events:
        print(f"  {_DIM}{'─' * 70}{_RESET}")
        max_dur = max((pe.duration for pe in result.perf_events), default=1.0)

        for pe in result.perf_events:
            name_lower = pe.name.lower()

            # Color-code by type
            if name_lower.startswith("tool:"):
                color = _YELLOW
            elif name_lower.startswith("llm call"):
                color = _CYAN
            elif "ttft" in name_lower or "first" in name_lower:
                color = _GREEN
            elif "total" in name_lower or "duration" in name_lower:
                color = _BOLD
            else:
                color = ""

            bar = _bar(pe.duration, max_dur, width=25)
            extra_str = ""
            if pe.extra:
                parts = [f"{k}={v}" for k, v in pe.extra.items()]
                extra_str = f"  {_DIM}({', '.join(parts)}){_RESET}"

            print(f"    {color}{pe.name:<40}{_RESET} {pe.duration:>7.3f}s  {_DIM}{bar}{_RESET}{extra_str}")

    # Client-side metrics
    print(f"  {_DIM}{'─' * 70}{_RESET}")
    print(f"    {'Client TTFT':<40} {result.client_ttft:>7.3f}s")
    print(f"    {'Client TPS':<40} {result.client_tps:>7.1f} tok/s")
    print(f"    {'Client Total Duration':<40} {result.client_duration:>7.3f}s")
    print(f"    {'Response':<40} {result.total_tokens:>5} chunks, {result.response_length:>5} chars")


def print_summary_table(results: list[BenchmarkResult]) -> None:
    """Print a compact summary table."""
    print()
    print(f"{_BOLD}{'=' * 120}{_RESET}")
    print(f"{_BOLD}  SUMMARY TABLE{_RESET}")
    print(f"{'=' * 120}")
    print(
        f"  {'#':>2}  {'Scenario':<30}  {'TTFT':>7}  {'1st LLM':>7}  "
        f"{'Think':>7}  {'Tools':>7}  {'LLM':>7}  {'Graph':>7}  "
        f"{'TPS':>6}  {'Status':>8}"
    )
    print(f"  {'-' * 116}")

    for r in results:
        status = f"{_GREEN}OK{_RESET}" if r.success else (
            f"{_RED}TMOUT{_RESET}" if r.timed_out else f"{_RED}ERR{_RESET}"
        )

        def _fmt(v: float) -> str:
            return f"{v:>6.2f}s" if v > 0 else f"{'  -':>7}"

        print(
            f"  {r.scenario_id:>2}  {r.scenario_name:<30}  "
            f"{_fmt(r.fastapi_ttft)}  {_fmt(r.first_llm_call)}  "
            f"{_fmt(r.llm_thinking)}  {_fmt(r.total_tool_time)}  {_fmt(r.estimated_llm_time)}  "
            f"{_fmt(r.total_graph_duration)}  {r.client_tps:>5.1f}  {status}"
        )

    print(f"  {'-' * 116}")

    # Aggregates
    successful = [r for r in results if r.success]
    if successful:
        n = len(successful)
        avg_ttft = sum(r.fastapi_ttft for r in successful) / n
        avg_1st_llm = sum(r.first_llm_call for r in successful) / n
        avg_think = sum(r.llm_thinking for r in successful) / n
        avg_tools = sum(r.total_tool_time for r in successful) / n
        avg_llm = sum(r.estimated_llm_time for r in successful) / n
        avg_graph = sum(r.total_graph_duration for r in successful) / n
        avg_tps = sum(r.client_tps for r in successful) / n

        def _fmt(v: float) -> str:
            return f"{v:>6.2f}s" if v > 0 else f"{'  -':>7}"

        print(
            f"  {'':>2}  {f'AVERAGES (n={n})':<30}  "
            f"{_fmt(avg_ttft)}  {_fmt(avg_1st_llm)}  "
            f"{_fmt(avg_think)}  {_fmt(avg_tools)}  {_fmt(avg_llm)}  "
            f"{_fmt(avg_graph)}  {avg_tps:>5.1f}"
        )

    print()

    # Success rate and totals
    total_time = sum(r.client_duration for r in results)
    print(f"  Success rate: {len(successful)}/{len(results)} ({100 * len(successful) / len(results):.0f}%)")
    print(f"  Total benchmark time: {total_time:.1f}s")

    # ── Bottleneck analysis ──
    if successful:
        print()
        print(f"  {_BOLD}BOTTLENECK ANALYSIS:{_RESET}")

        # Find where time is spent on average
        avg_tools_pct = (avg_tools / avg_graph * 100) if avg_graph > 0 else 0
        avg_llm_pct = (avg_llm / avg_graph * 100) if avg_graph > 0 else 0
        print(f"    Avg time split:  LLM {avg_llm_pct:.0f}%  |  Tools {avg_tools_pct:.0f}%")

        # Slowest scenario
        slowest = max(successful, key=lambda r: r.total_graph_duration)
        print(f"    Slowest scenario: #{slowest.scenario_id} {slowest.scenario_name} ({slowest.total_graph_duration:.1f}s)")

        # Highest TTFT
        highest_ttft = max(successful, key=lambda r: r.fastapi_ttft)
        print(f"    Highest TTFT:     #{highest_ttft.scenario_id} {highest_ttft.scenario_name} ({highest_ttft.fastapi_ttft:.1f}s)")

        # Slowest individual tool call across all scenarios
        all_tool_calls = []
        for r in successful:
            for tc in r.tool_calls:
                all_tool_calls.append((r.scenario_id, tc["name"], tc["duration"]))
        if all_tool_calls:
            slowest_tool = max(all_tool_calls, key=lambda x: x[2])
            print(f"    Slowest tool call: {slowest_tool[1]} in #{slowest_tool[0]} ({slowest_tool[2]:.1f}s)")

        # Category breakdown
        categories: dict[str, list] = {}
        for r in successful:
            categories.setdefault(r.category, []).append(r)

        if categories:
            print()
            print(f"  {_BOLD}BY CATEGORY:{_RESET}")
            for cat, cat_results in sorted(categories.items()):
                n_cat = len(cat_results)
                cat_avg_ttft = sum(r.fastapi_ttft for r in cat_results) / n_cat
                cat_avg_graph = sum(r.total_graph_duration for r in cat_results) / n_cat
                cat_avg_tools = sum(r.total_tool_time for r in cat_results) / n_cat
                cat_avg_llm = sum(r.estimated_llm_time for r in cat_results) / n_cat
                print(
                    f"    {cat:<12}  TTFT: {cat_avg_ttft:>5.1f}s  "
                    f"Graph: {cat_avg_graph:>5.1f}s  "
                    f"Tools: {cat_avg_tools:>5.1f}s  "
                    f"LLM: {cat_avg_llm:>5.1f}s  "
                    f"(n={n_cat})"
                )

    print(f"{'=' * 120}")


def save_results(results: list[BenchmarkResult]) -> None:
    """Save results to JSON file."""
    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "backend_url": BACKEND_URL,
        "scenario_count": len(results),
        "success_count": sum(1 for r in results if r.success),
        "results": [],
    }

    for r in results:
        entry = {
            "scenario_id": r.scenario_id,
            "scenario_name": r.scenario_name,
            "category": r.category,
            "client_metrics": {
                "ttft_seconds": r.client_ttft,
                "tps": r.client_tps,
                "total_duration_seconds": r.client_duration,
                "total_tokens": r.total_tokens,
                "response_length_chars": r.response_length,
            },
            "backend_metrics": {
                "fastapi_ttft_seconds": r.fastapi_ttft,
                "backend_ttft_seconds": r.backend_ttft,
                "first_llm_call_seconds": r.first_llm_call,
                "llm_thinking_seconds": r.llm_thinking,
                "total_tool_time_seconds": r.total_tool_time,
                "estimated_llm_time_seconds": r.estimated_llm_time,
                "total_graph_duration_seconds": r.total_graph_duration,
                "total_request_duration_seconds": r.total_request_duration,
            },
            "tool_calls": r.tool_calls,
            "llm_calls": r.llm_calls,
            "perf_timeline": [
                {"name": pe.name, "duration": pe.duration, **pe.extra}
                for pe in r.perf_events
            ],
            "success": r.success,
            "timed_out": r.timed_out,
            "error": r.error or None,
        }
        output["results"].append(entry)

    # Aggregates
    successful = [r for r in results if r.success]
    if successful:
        n = len(successful)
        output["aggregates"] = {
            "avg_fastapi_ttft_seconds": round(sum(r.fastapi_ttft for r in successful) / n, 3),
            "avg_first_llm_call_seconds": round(sum(r.first_llm_call for r in successful) / n, 3),
            "avg_llm_thinking_seconds": round(sum(r.llm_thinking for r in successful) / n, 3),
            "avg_total_tool_time_seconds": round(sum(r.total_tool_time for r in successful) / n, 3),
            "avg_estimated_llm_time_seconds": round(sum(r.estimated_llm_time for r in successful) / n, 3),
            "avg_total_graph_duration_seconds": round(sum(r.total_graph_duration for r in successful) / n, 3),
            "avg_client_tps": round(sum(r.client_tps for r in successful) / n, 1),
            "total_benchmark_seconds": round(sum(r.client_duration for r in results), 3),
            "success_rate": round(len(successful) / len(results), 2),
        }

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n  Results saved to: {RESULTS_FILE}")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print(f"{_BOLD}{'=' * 70}{_RESET}")
    print(f"{_BOLD}Aria Agent Performance Benchmark{_RESET}")
    print(f"Backend: {BACKEND_URL}")
    print(f"Scenarios: {len(SCENARIOS)}")
    print(f"Timeout: {TIMEOUT}s per scenario")
    print(f"{'=' * 70}")
    print()

    # Check backend is running
    try:
        httpx.get(f"{BACKEND_URL}/docs", timeout=5)
    except httpx.ConnectError:
        print(f"{_RED}ERROR: Cannot connect to backend at {BACKEND_URL}{_RESET}")
        print("Start the backend first:")
        print('  "agent/.venv/Scripts/uvicorn.exe" backend.main:app --host 127.0.0.1 --port 8001')
        sys.exit(1)

    results: list[BenchmarkResult] = []

    # Optional: run only specific scenario(s) via CLI arg
    scenarios_to_run = SCENARIOS
    if len(sys.argv) > 1:
        try:
            ids = [int(x) for x in sys.argv[1:]]
            scenarios_to_run = [s for s in SCENARIOS if s["id"] in ids]
            if not scenarios_to_run:
                print(f"{_RED}No matching scenario IDs: {ids}{_RESET}")
                sys.exit(1)
        except ValueError:
            pass  # not numeric args, run all

    for scenario in scenarios_to_run:
        print(f"{_BOLD}[{scenario['id']:>2}/{len(SCENARIOS)}] {scenario['name']}{_RESET}")
        print(f"       {_DIM}{scenario['prompt'][:80]}{'...' if len(scenario['prompt']) > 80 else ''}{_RESET}")

        result = run_scenario(scenario)
        results.append(result)

        # Print detailed breakdown for each scenario
        print_scenario_detail(result)
        print()

    # Final summary
    print_summary_table(results)
    save_results(results)


if __name__ == "__main__":
    main()

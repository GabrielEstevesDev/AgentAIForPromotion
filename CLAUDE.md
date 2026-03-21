# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AgenticStack** is a full-stack AI-powered e-commerce assistant designed as a demo-ready product for potential clients.

- **Frontend**: Next.js 15 (App Router) with React 19, Tailwind CSS 4, Vercel AI SDK (`useChat`). Port **3000**.
- **Backend**: FastAPI with SSE streaming, wrapping an **explicit LangGraph StateGraph agent** backed by `gpt-4o-mini`. Port **8001**.

The agent queries a SQLite e-commerce database, an internal knowledge base (RAG via ChromaDB), and the live web (Tavily). It supports an **Approval (HITL)** workflow for high-risk actions. Conversations/messages are persisted in SQLite.

The UI has **three tabs**: Chat, Database Explorer, and Knowledge Base.

## Quick Start

### Prerequisites
- **Node.js 20+** / **npm**, **Python 3.11+** with `agent/.venv`
- API keys in `agent/.env`: `OPENAI_API_KEY`, `TAVILY_API_KEY`

### Commands
```bash
# Ingest RAG docs (once)
cd agent && python -m rag.ingest

# Backend (port 8001)
"agent/.venv/Scripts/uvicorn.exe" backend.main:app --host 127.0.0.1 --port 8001

# Frontend (port 3000)
npm run dev
```

## Architecture

### Directory Structure

```
src/                          — Next.js frontend (App Router)
  app/
    chat/[id]/page.tsx        — Conversation page (SSR, loads history)
    database/page.tsx         — Browse all DB tables with pagination
    documents/page.tsx        — RAG docs as markdown + PDF download
    api/
      chat/route.ts           — Bridges Vercel AI SDK ↔ FastAPI SSE
      conversations/          — CRUD + messages + traces endpoints
      charts/route.ts         — Serves chart PNGs
    components/
      ConversationClient.tsx  — useChat, approval state, drawer orchestration
      ChatArea.tsx            — Message list, 5 front actions, typing indicator
      MessageBubble.tsx       — SQL tabs, approval cards, JSON extraction, trace inspector
      TracePanel.tsx          — Collapsible trace inspector (node flow, tools, LLM calls, timeline)
      HitlApproval.tsx        — Full-width approval card (2-column, amber header)
      UseCasesDrawer.tsx      — 5-tab drawer (SQL, RAG, WEB, Charts, Approval)
      Sidebar.tsx             — 3-tab nav (Chat/Database/Documents), conversation list
  lib/
    api.ts / server-api.ts    — Client/server fetch helpers
    session.ts                — Per-tab session ID (sessionStorage UUID)
    parsers.ts                — JSON block extraction (USE_CASE_CARDS, HITL_REQUEST)

backend/                      — FastAPI backend (Python)
  main.py                     — App, CORS, lifespan, structlog, RequestIdMiddleware
  agent.py                    — Facade: delegates to graph/ or agent_legacy.py
  mode_classifier.py          — Mode classifier (greeting/direct_query/off_topic/factual/analytical/chart/hitl/rag/prospecting) + jailbreak & vague-prompt detection
  validators.py               — Post-processing: coherence check, HITL validation, length monitoring
  config.py                   — All settings (LLM_MODEL, DB_PATH, etc.)
  db.py                       — SQLite connection (dict_factory, WAL, 30s timeout)
  graph/
    state.py                  — AgenticStackState TypedDict
    nodes.py                  — Node functions + Runnable chains (plan_and_call, force_respond, post_approve)
    edges.py                  — Conditional routing
    builder.py                — build_graph() with MemorySaver
    stream.py                 — SSE streaming, heartbeat, SQL injection, HITL resume, perf tracking
  core/
    system_prompt.py          — Core prompt (~500 tokens): identity, 6 rules, output discipline
    mode_templates.py         — Per-mode templates (injected only for matching mode)
  routers/
    chat.py                   — POST /api/chat (SSE), trace persistence to MessageTrace table
    conversations.py          — CRUD + messages + traces endpoints
    charts.py / documents.py / database_explorer.py / purchase_orders.py
  tools/                      — 6 agent tools (see below)
  queries/library.py          — 44+ named pre-built SQL queries
  rag/                        — ingest.py + retriever.py (ChromaDB)
  scripts/
    export_traces.py          — Export all conversations + traces to JSON
  tests/
    eval_prompts.py           — 23-prompt eval harness (PASS/WARN/FAIL)

agent/                        — Original standalone agent (.venv, Gradio UI, CLI)
docs/                         — RAG knowledge base (11 Markdown files)
dev.db                        — SQLite database (Prisma-generated schema)
```

### Request Flow

1. User types a message → `useChat` → Next.js `/api/chat/route.ts` → proxies to `POST /api/chat` on FastAPI
2. FastAPI runs the StateGraph:
   - **summarize_if_needed**: Condenses conversations > 12 messages
   - **classify**: Sets response mode, detects HITL/PO intent, checks for direct query or greeting match
   - **Fast lanes** (no LLM): greeting → `fast_response` → END; direct_query → `direct_query` → END; off_topic (jailbreaks, vague prompts) → `fast_response` → END; chart → `direct_chart` → END
   - **plan_and_call**: LLM with tools → **execute_tools** → loops until `tool_call_count >= max_tool_calls` → **force_respond** (LLM without tools)
   - **extract_hitl** → **hitl_gate** (calls `interrupt()` if HITL detected) → **assemble_response** → **validate**
3. `stream.py` injects SQL blocks, emits heartbeats, tracks performance metrics
4. HITL: user Approve/Reject → `Command(resume=decision)` → **post_approve** node
5. After streaming: messages + traces persisted to SQLite, auto-title generated

### Trace Inspector

Each assistant message can have trace data showing the full graph execution path. Traces are stored in the `MessageTrace` table and displayed via `TracePanel.tsx` below each assistant message bubble.

**Access traces:**
- **UI**: Click the "Trace Inspector" bar below any assistant message
- **API**: `GET /api/conversations/{id}/traces` (all) or `GET /api/conversations/{id}/traces/{messageId}` (single)
- **Export script**: `"agent/.venv/Scripts/python.exe" backend/scripts/export_traces.py` → outputs `backend/scripts/conversations_with_traces.json`

### Key Features

**SQL Query Tabs**: `sql_query` results are auto-prefixed with SQL (injected in `stream.py`). `MessageBubble` renders as tabbed `SqlResultsBlock` (Results / SQL Query).

**Charts**: `python_executor` with matplotlib → PNG saved to `backend/charts/` → served via `/api/charts/{uuid}.png` → rendered as `<img>` in messages.

**Approval (HITL)**: 3 use cases (Refund Email, Promotion Strategy, Purchase Order). 3-layer enforcement: graph `interrupt()`, PO intent guard in tool, system prompt rules. UI renders `HitlApproval` card outside message bubble.

**Use Cases Drawer**: 5 tabs (SQL, RAG, WEB, Charts, Approval). Internal ID `"HITL"` displays as `"Approval"` via `BADGE_LABELS`.

**Purchase Orders**: Full lifecycle (Draft → Approved → Sent → Received). `purchase_order_action` tool blocked unless PO intent + approval. Demo mode auto-receives on approve.

**Rate Limiting**: Per-user and global daily rate limits protect API costs for the public demo. Backend checks run in `routers/chat.py` before agent execution, using the `RateLimit` SQLite table with IP-based user identification (`request.client.host`). Returns HTTP 429 with structured JSON (`global_limit` / `user_limit`). Admin bypass via `x-admin-token` header matched against `ADMIN_SECRET_TOKEN` env var. Frontend intercepts 429 errors in `ConversationClient.tsx` (`onError` + `hadStreamErrorRef` to prevent navigation on error) and renders styled `RateLimitBanner` in `ChatArea.tsx` (amber for user limit, blue for global limit). Admin token read from `localStorage("adminToken")`.

**Session Isolation**: Per-tab conversation isolation for the public demo. Each browser tab generates a UUID stored in `sessionStorage` (`src/lib/session.ts`). The `Conversation` table has a `sessionId` column; `list_conversations` filters by it. Closing a tab = blank slate. Old conversations with `NULL` sessionId are hidden and GC'd within 24h. This is UX isolation, not a security boundary.

**Prompt Injection Defense**: 2-layer defense-in-depth. Layer 1: `mode_classifier.py` regex patterns catch jailbreak/persona-injection/prompt-extraction attempts and route to off-topic fast lane (no LLM, no tools). Layer 2: `system_prompt.py` security shield instructs the LLM to politely redirect novel bypasses without acknowledging internal configuration.

### Streaming Architecture Note

LLM-calling nodes **must** be Runnable chains (`RunnableLambda | ChatOpenAI | RunnableLambda`), not function nodes with `llm.ainvoke()`. Required for `astream_events(version="v2")` to capture tokens. The three Runnable chains: `plan_and_call`, `force_respond`, `post_approve`.

## Agent Tools (6 total)

| Tool | Purpose |
|------|---------|
| `query_library` | Pre-built SQL by name (44+ queries). **Preferred** over `sql_query`. |
| `sql_query` | Read-only SQL SELECT. Max 100 rows. Use when no library query fits. |
| `rag_search` | Semantic search over internal docs (ChromaDB, top-5). |
| `web_search` | Tavily web search (max 5 results). |
| `python_executor` | Python subprocess (30s timeout). Captures matplotlib charts. |
| `purchase_order_action` | PO lifecycle. **Blocked unless PO intent + approval.** |

### Query Library Categories

Sales/Revenue, Products, Inventory, Orders, Customers, Reviews, API Usage, Suppliers & POs, Prospecting. To add: edit `QUERY_LIBRARY` in `backend/queries/library.py`.

## Database Schema

SQLite (`dev.db`), Prisma-generated **camelCase columns**.

**Critical rules:**
- `"Order"` must be quoted (reserved word)
- camelCase columns: `firstName`, `customerId`, `orderDate`, etc.
- Only `SELECT` permitted (except `purchase_order_action`)
- Never expose UUIDs/SKUs in customer-facing content
- `db.py` uses `dict_factory` — always use `row["key"]`, never positional

**Tables:** `Customer`, `Product`, `"Order"`, `OrderItem`, `Inventory`, `Review`, `ApiUsage`, `Supplier`, `PurchaseOrder`, `PurchaseOrderItem`, `Conversation`, `Message`, `MessageTrace`, `RateLimit`

**Seed data:** 60 customers, 240 products (12 categories), 80 orders, ~800 reviews, 1 supplier.

## Key Configuration (`backend/config.py`)

| Variable | Default | Purpose |
|---|---|---|
| `LLM_MODEL` | `gpt-4o-mini-2024-07-18` | OpenAI chat model |
| `DB_PATH` | `../dev.db` | SQLite path (relative to `agent/`) |
| `USE_LEGACY_AGENT` | `False` | Set `True` for old create_react_agent |
| `BACKEND_BASE_URL` | `http://127.0.0.1:8001` | Used by python_tool for chart URLs |
| `ADMIN_SECRET_TOKEN` | `""` | Admin token for rate-limit bypass |
| `RATE_LIMIT_GLOBAL` | `100` | Max daily messages across all users |
| `RATE_LIMIT_USER` | `10` | Max daily messages per IP address |

Frontend backend URL: `src/lib/backend.ts` (`http://localhost:8001`).

## Performance Optimizations

- **Direct query routing**: 23 regex patterns in `mode_classifier.py` skip LLM entirely for simple questions
- **Greeting fast lane**: Canned responses, no LLM call
- **Off-topic / security fast lane**: Jailbreak attempts, prompt injection, and vague prompts routed to canned off-topic response (no LLM, no tools)
- **Chart fast lane**: Chart requests routed to `direct_chart` node, skipping `plan_and_call`
- **Conversation summarization**: Condenses older messages when > 12 messages
- **Result caching**: 60s TTL in `sql_tool.py` and `query_library.py`
- **Async SQLite**: `aiosqlite` for non-blocking DB access
- **LLM fallbacks**: `.with_fallbacks()` + `.with_retry(stop_after_attempt=2)`
- **Prompt prefix caching**: Core prompt as separate SystemMessage enables OpenAI caching
- **Structured logging**: `structlog` with `X-Request-ID` tracing
- **Perf events**: `stream.py` emits TTFT, LLM time, tool time, graph duration via SSE
- **Rate limiting**: IP-based daily limits (per-user + global) checked before agent execution, avoids unnecessary LLM calls

## Common Tasks

- **Add a pre-built query**: Edit `QUERY_LIBRARY` in `backend/queries/library.py`
- **Add a new tool**: Create in `backend/tools/`, add to `ALL_TOOLS`. Put schema in docstring, not system_prompt.py.
- **Add RAG docs**: Place `.md` in `docs/`, run `python -m rag.ingest` from `agent/`
- **Add an approval use case**: Define in `backend/core/mode_templates.py`, add card to `UseCasesDrawer.tsx`
- **Modify system prompt**: `backend/core/system_prompt.py` (core) or `backend/core/mode_templates.py` (per-mode)
- **Tune response mode**: Edit `backend/mode_classifier.py` (max_tokens, max_tool_calls, patterns)
- **Add a direct query route**: Add `(regex, query_name)` to `_DIRECT_ROUTES` in `mode_classifier.py`
- **Run eval harness**: `"agent/.venv/Scripts/python.exe" backend/tests/eval_prompts.py` (backend must be running)
- **Export conversations + traces**: `"agent/.venv/Scripts/python.exe" backend/scripts/export_traces.py`
- **Test the app**: Start both servers, use Playwright MCP to navigate to `http://localhost:3000`
- **Adjust rate limits**: Set `RATE_LIMIT_GLOBAL` and `RATE_LIMIT_USER` env vars (or edit `backend/config.py`). Set `ADMIN_SECRET_TOKEN` for admin bypass. Store admin token in browser via `localStorage.setItem("adminToken", "<token>")`

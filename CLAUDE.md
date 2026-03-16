# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Aria** is a full-stack AI-powered e-commerce assistant designed as a demo-ready product for potential clients. It consists of:

- **Frontend**: Next.js 15 (App Router) with React 19, Tailwind CSS 4, and the Vercel AI SDK (`useChat` hook). Runs on port **3000**.
- **Backend**: FastAPI with SSE streaming, wrapping an **explicit LangGraph StateGraph agent** backed by `gpt-4o-mini`. Runs on port **8001**.

The agent answers questions about a SQLite e-commerce database, an internal knowledge base (RAG via ChromaDB), and the live web (via Tavily). It supports an **Approval (HITL)** workflow for high-risk actions (refunds, promotions, purchase orders). Conversations and messages are persisted in SQLite via direct SQL (not Prisma at runtime).

The UI has **three main tabs**: Chat (agent conversation), Database Explorer (browse all tables), and Knowledge Base (view RAG documents with PDF export).

## Quick Start

### Prerequisites
- **Node.js 20+** and **npm** (for the frontend)
- **Python 3.11+** with `agent/.venv` virtual environment
- API keys: `OPENAI_API_KEY` and `TAVILY_API_KEY`

### Environment setup

Create `agent/.env` (root `.env` works as fallback):
```
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...
```

### Ingest RAG documents (once, before first run)
```bash
cd agent
python -m rag.ingest
```
Re-running is safe — does a full collection replacement.

### Run the backend (FastAPI) — port 8001
```bash
"agent/.venv/Scripts/uvicorn.exe" backend.main:app --host 127.0.0.1 --port 8001
# API available at http://127.0.0.1:8001
```

### Run the frontend (Next.js)
```bash
npm run dev
# UI available at http://localhost:3000
```

## Architecture

### Full-Stack Structure

```
root/
  src/                        — Next.js frontend (App Router)
    app/
      layout.tsx              — Root layout with ThemeProvider
      page.tsx                — Redirects to /chat
      chat/
        layout.tsx            — Chat layout (uses AppShell)
        page.tsx              — New conversation page (SSR)
        [id]/page.tsx         — Existing conversation page (SSR, loads history)
      database/
        layout.tsx            — Database Explorer layout (uses AppShell)
        page.tsx              — Browse all DB tables with pagination
      documents/
        layout.tsx            — Knowledge Base layout (uses AppShell)
        page.tsx              — View RAG docs rendered as markdown + PDF download
      api/
        chat/route.ts         — Bridges Vercel AI SDK ↔ FastAPI SSE stream
        conversations/
          route.ts            — GET list, POST create
          [id]/route.ts       — PATCH rename, DELETE
          [id]/messages/route.ts — GET message history
      components/
        AppShell.tsx          — Shared layout wrapper (Sidebar + main content area)
        ConversationClient.tsx — Client shell: useChat, approval state, drawer orchestration
        ChatArea.tsx          — Message list, 5 front actions, Use Cases button, typing indicator
        ChatInput.tsx         — Textarea input with send + Use Cases drawer button
        MessageBubble.tsx     — Renders messages: SQL tabs, approval cards (outside bubble), JSON block extraction, streaming placeholder
        UseCasesDrawer.tsx    — Slide-over drawer with 5 category tabs + card grid
        HitlApproval.tsx      — Full-width approval card (2-column layout, amber gradient header, controls + evidence, on_approve/on_reject info)
        Sidebar.tsx           — Navigation tabs (Chat/Database/Documents), conversation list, rename, delete
        ThemeToggle.tsx       — Light/dark mode toggle
        ThemeProvider.tsx     — next-themes provider
    lib/
      api.ts                  — Client-side fetch helpers (conversations API)
      server-api.ts           — Server-side fetch helpers (SSR data loading)
      backend.ts              — BACKEND_URL constant (http://localhost:8001)
      types.ts                — Shared TypeScript types (UseCaseCard, HITL payloads)
      parsers.ts              — JSON block extraction (USE_CASE_CARDS, HITL_REQUEST)

  backend/                    — FastAPI backend (Python)
    main.py                   — FastAPI app, CORS, lifespan (builds agent), structlog configuration, RequestIdMiddleware
    agent.py                  — Thin facade: delegates to graph/ (StateGraph) or agent_legacy.py based on USE_LEGACY_AGENT flag
    agent_legacy.py           — Legacy create_react_agent implementation (fallback, USE_LEGACY_AGENT=True)
    mode_classifier.py        — Response-mode classifier (greeting/direct_query/factual/analytical/chart/hitl/rag/prospecting) — sets max_tokens + tool budget per request; includes direct query routing (23 pattern→query mappings)
    validators.py             — Programmatic post-processing: summary/breakdown coherence check, HITL structure validation, response length monitoring
    config.py                 — All settings (LLM_MODEL, DB_PATH, CHARTS_DIR, USE_LEGACY_AGENT, etc.)
    db.py                     — SQLite connection with dict_factory, WAL mode, 30s timeout
    hitl_state.py             — Per-thread approval tracking + PO intent tracking (legacy only, used by agent_legacy.py)
    graph/                    — Explicit StateGraph agent (replaces black-box ReAct loop)
      __init__.py             — Exports build_graph() and stream_graph()
      state.py                — AriaState TypedDict (messages, mode, tool_call_count, captured_sqls, HITL fields, po_intent, summary)
      nodes.py                — Node functions and Runnable chains: summarize_if_needed, classify, fast_response, direct_query, execute_tools, extract_hitl, hitl_gate, assemble_response, validate (functions); plan_and_call, force_respond, post_approve (Runnable chains for LLM streaming). LLM instances use .with_fallbacks() and .with_retry(stop_after_attempt=2).
      edges.py                — Conditional routing: route_after_plan, route_after_tools, route_after_hitl_check
      builder.py              — build_graph() assembles and compiles the StateGraph with MemorySaver
      stream.py               — stream_graph() SSE streaming with heartbeat, timeout, SQL injection, HITL resume via Command(resume=...), performance event tracking (PERF: markers), tool status emoji messages
    core/
      system_prompt.py        — Core system prompt (~500 tokens): identity, 6 rules, output discipline, self-check. Templates and schema moved to mode_templates.py and tool docstrings.
      mode_templates.py       — Per-mode instruction templates (factual/analytical/chart/hitl/rag/prospecting). Injected as SystemMessage only for the matching mode.
    routers/
      chat.py                 — POST /api/chat — SSE streaming endpoint
      conversations.py        — CRUD endpoints for conversations + messages
      charts.py               — GET /api/charts/{filename} — serves chart PNG files
      purchase_orders.py      — Supplier PO CRUD + approve/receive with inventory updates
      database_explorer.py    — GET /api/database/tables — browse DB tables with pagination
      documents.py            — GET /api/documents — serve RAG docs as markdown + PDF (fpdf2)
    tools/
      query_library.py        — Pre-built SQL query lookup by name (44+ queries); 60s TTL result cache; async via aiosqlite
      sql_tool.py             — Read-only SQL SELECT; returns results as markdown table; 60s TTL result cache; async via aiosqlite
      rag_tool.py             — Delegates to rag/retriever.py (ChromaDB)
      search_tool.py          — Tavily web search (max 5 results)
      python_tool.py          — Python subprocess executor; captures matplotlib charts as PNG
      purchase_order_tool.py  — LangGraph tool for managing supplier POs (create/approve/receive) with code-level intent guard + approval guard
    queries/
      library.py              — Dict of 44 named pre-built SQL queries (add entries here to expand)
    rag/
      ingest.py               — Chunks docs/*.md → ChromaDB (safe to re-run)
      retriever.py            — lru_cache Chroma vectorstore singleton
    charts/                   — Saved chart PNGs (auto-cleaned after 1h)
    chroma_db/                — Persisted ChromaDB vectorstore (auto-generated)
    tests/
      eval_prompts.py         — Evaluation harness: 23 test prompts with pass/fail criteria
      benchmark_results.json  — Performance benchmark results (10 scenarios, timing metrics)

  agent/                      — Original standalone agent (Gradio UI + CLI)
    .venv/                    — Python virtual environment (used by backend too)
    app.py                    — Gradio web UI (port 7860) — legacy standalone mode
    main.py                   — CLI REPL (/exit, /reset, /tools) — legacy
    requirements.txt          — Python dependencies (langgraph, langchain, aiosqlite, structlog, matplotlib, etc.)

  skills/                     — Reference skill modules (LangChain/LangGraph best practices)
    .agents/skills/           — 5 skill modules: deep-agents-core, deep-agents-orchestration, langchain-rag, langgraph-fundamentals, langgraph-human-in-the-loop
    skills-lock.json          — Skill versions and hashes

  docs/                       — RAG knowledge base (11 Markdown files, includes capability-use-case-map.md)
  dev.db                      — SQLite database (Prisma-generated schema)
  prisma/                     — Prisma schema (used for migrations only)
  guidelines.md               — Product guidelines (USE_CASE_CARDS, HITL, output style)
```

### Request Flow

1. User types a message in the browser (`ConversationClient`)
2. If no conversation exists yet, a new one is created via `POST /api/conversations`
3. `useChat` sends a request to Next.js route `/api/chat/route.ts`
4. The Next.js route proxies to `POST http://127.0.0.1:8001/api/chat` and bridges the FastAPI SSE stream into the Vercel AI SDK data stream format (`0:` text tokens, `d:` done)
5. FastAPI's `stream_agent` delegates to `stream_graph()` which runs the Aria StateGraph:
   - **summarize_if_needed node**: If conversation > 12 messages, condenses older messages into a summary (keeps last 6 verbatim) using a dedicated summarizer LLM
   - **classify node**: Classifies user message into a response mode via `mode_classifier.py`, detects HITL approval and PO intent, checks for direct query match and greeting patterns
   - **Fast lanes** (skip LLM entirely):
     - **greeting** → `fast_response` node → END (canned responses, no LLM call)
     - **direct_query** → `direct_query` node → END (executes matched query_library entry directly)
   - **plan_and_call node**: LLM with tools bound produces either tool calls or text (two SystemMessages: core prompt + mode template, enables prompt prefix caching)
   - **execute_tools node**: Runs tool calls, increments `tool_call_count` in graph state, captures SQL from `sql_query`
   - **Conditional edge (route_after_tools)**: If `tool_call_count < max_tool_calls` → loops back to `plan_and_call`; else → `force_respond`
   - **force_respond node**: LLM *without* tools bound (physically cannot call tools), receives a SystemMessage to produce final answer
   - **extract_hitl node**: Scans AI response for `HITL_REQUEST` JSON blocks
   - **hitl_gate node** (if HITL detected): Calls `interrupt()` — graph pauses, SSE stream ends with the HITL_REQUEST content
   - **assemble_response + validate nodes**: Build final response text, run coherence/HITL validators
   - The streaming layer (`stream.py`) captures SQL from `on_tool_end` events and injects ` ```sql ` blocks before the first text token
   - **Performance tracking**: `stream.py` emits `\x00PERF:` markers for TTFT, LLM thinking time, tool execution time, and total graph duration — forwarded as `perf` SSE events to the frontend
6. For HITL approval: user clicks Approve → `[HITL Response]` message → `stream_graph()` detects this and resumes the graph via `Command(resume=decision)` → **post_approve** node produces the final artifact
7. After streaming completes, `chat.py` runs post-processing validators. Messages are persisted to SQLite. Auto-title is generated for the first exchange.
8. `onFinish` in `useChat` fires `aria:conversation-updated` DOM events to refresh the sidebar

### SQL Query Tab Feature

When the agent uses `sql_query`, the response content is automatically prefixed with the SQL in a ` ```sql ` fenced block (injected in `graph/stream.py`, not by the LLM). `MessageBubble` parses the content and detects ` ```sql ``` + markdown table` pairs, rendering them as a unified `SqlResultsBlock` component with:
- **Results tab** (default) — styled table with "Copy CSV" button
- **SQL Query tab** — exact SQL with "Copy SQL" button

The SQL injection happens at the streaming layer (`stream_graph` in `graph/stream.py`) via `on_tool_end` events, making it 100% reliable regardless of LLM behavior.

### Chart Feature

When the agent uses `python_executor` with matplotlib:
1. The tool injects a preamble (`matplotlib.use('Agg')`) and a postamble that captures figures
2. Charts are saved as PNG files to `backend/charts/` with a UUID filename
3. The tool returns `![chart](http://127.0.0.1:8001/api/charts/{uuid}.png)` markdown
4. The LLM includes this in its response; `MessageBubble` renders it as an `<img>`
5. `GET /api/charts/{filename}` serves the PNG; files older than 1h are auto-deleted

### Approval (HITL) Feature

The system uses a Human-in-the-Loop approval workflow. The UI labels this as "Approval" (not "HITL") for user-facing purposes.

When the agent encounters a high-risk action (refund email, promotion, purchase order), it:
1. Performs analysis and gathers evidence using tools (SQL, RAG, etc.)
2. Outputs a `HITL_REQUEST` JSON block inside a ` ```json ``` ` code fence
3. `MessageBubble` detects and extracts the JSON via `extractStructuredBlocks()` from `src/lib/parsers.ts`
4. During streaming, partial `HITL_REQUEST` JSON blocks are hidden and replaced with a "Creating approval..." placeholder (amber card with spinner)
5. `HitlApproval` component renders as a **full-width card outside the message bubble**: amber gradient header, 2-column layout (evidence/preview left, controls right), action bar at bottom
6. User action is sent as a `[HITL Response]` message back to the agent
7. Agent produces the final artifact (email, strategy, purchase order) or adjusts based on feedback

**Code-level enforcement** (3 layers):
1. **Native interrupt** (`backend/graph/nodes.py` — `hitl_gate`): When a HITL_REQUEST is detected in the AI response, the graph calls `interrupt()` which pauses execution. The graph resumes only when the user approves via `Command(resume=decision)`. Approval and PO intent are tracked in graph state (`hitl_approved`, `po_intent`), not global dicts. The `execute_tools` and `post_approve` nodes inject these into the config so tools can check them.
2. **PO intent guard** (`purchase_order_tool.py`): In StateGraph mode, reads `po_intent` and `hitl_approved` from the config's `configurable` dict (set by graph nodes). In legacy mode, falls back to `hitl_state.py` global dicts.
3. **System prompt rules** (`backend/core/system_prompt.py`): 6 core rules (mandatory approval, stay on topic, PO only for replenishment, speed/tool budget, single source per metric, no charts in HITL pre-approval). HITL contract and use case specs are in `backend/core/mode_templates.py` and only injected for HITL-mode requests.

**3 required approval use cases:**
- **Refund/Dispute Email** — RAG + SQL → email draft with tone/resolution controls. Email must include product names (not IDs) and total refund amount. After approval: final email + "email sending not configured" demo note.
- **30-Day Promotion Strategy** — SQL + charts → strategy with revenue baseline, category share, product tiers (Promote/Hold/Liquidate), KPI targets, budget/discount controls
- **Replenishment + Purchase Order** — SQL + charts → PO draft with per-item velocity, days of cover, suggested qty, line costs, grand total, budget controls, auto-receives inventory on approval

**Customer-facing content rules:**
- Never expose internal IDs, UUIDs, or SKUs in emails or customer messages
- Always resolve product names via JOIN queries
- Always include total amounts from the Order table

### Use Cases Drawer Feature

The UI shows 5 front starter action cards (one per category: SQL, RAG, WEB, PYTHON_CHART, Approval) and a "Browse All Use Cases" button that opens a slide-over drawer with 5 tabs and card grids. Cards populate the chat input with ready-to-run prompts.

The internal category ID remains `"HITL"` but displays as **"Approval"** in all user-facing UI (tab labels, badge text). Badge display mapping is in `BADGE_LABELS` in both `ChatArea.tsx` and `UseCasesDrawer.tsx`.

The LLM can dynamically provide use case cards by outputting a `USE_CASE_CARDS` JSON block, which updates the drawer data at runtime.

### Purchase Order & Replenishment Flow

The system supports a full supplier purchase order lifecycle:
1. **Supplier** — 1 demo supplier (EcoSource Trading) seeded in the database
2. **PO Creation** — Draft POs with line items (existing products or new SKUs). Tool auto-resolves `productId` from SKU or product name.
3. **PO Approval** — Status transitions: Draft → Approved → Sent → Received
4. **Inventory Update** — On receive, stock levels are updated. Tool resolves existing products by SKU/name before creating new ones.
5. **Demo Mode** — `auto_receive_on_approve=true` skips the Sent step and immediately updates inventory

The agent uses `purchase_order_action` tool after approval. The REST API at `/api/purchase-orders` also exposes these operations directly.

**PO intent guard**: The `purchase_order_action` tool is completely blocked unless the user has explicitly mentioned PO/replenishment keywords in the conversation. In StateGraph mode, `po_intent` is tracked in graph state and passed to tools via augmented config. In legacy mode, falls back to `has_po_intent()` from `hitl_state.py`.

### Database Explorer Feature (`/database`)

A standalone tab that lets users browse all database tables:
- Left panel lists all tables with row counts
- Main area shows a paginated data table with sticky headers
- Backend: `GET /api/database/tables` (list) and `GET /api/database/tables/{name}?limit=100&offset=0` (rows)

### Knowledge Base Feature (`/documents`)

A standalone tab that shows the RAG knowledge base documents:
- Left panel lists all 10 markdown documents from `docs/` with file sizes
- Main area renders the selected document as styled markdown
- "Download PDF" button generates a PDF via `fpdf2` on the backend
- Backend: `GET /api/documents` (list), `GET /api/documents/{filename}` (content), `GET /api/documents/{filename}/pdf` (PDF)

### Navigation

The `Sidebar` component includes a 3-tab navigation bar:
- **Chat** (MessageSquare icon) — conversation list with create/rename/delete
- **Database** (Database icon) — database explorer
- **Documents** (FileText icon) — knowledge base viewer

The conversations list only appears when on the Chat tab. All tabs share the `AppShell` layout component.

## Agent Tools (6 total)

| Tool | File | Purpose |
|------|------|---------|
| `query_library` | `backend/tools/query_library.py` | Execute a pre-built SQL query by name. **Preferred over `sql_query`** for common questions — skips LLM SQL generation entirely. Call with `query_name='list'` to enumerate. |
| `sql_query` | `backend/tools/sql_tool.py` | Read-only SQL SELECT against `dev.db`. Returns markdown table. Max 100 rows. Use when no library query fits. |
| `rag_search` | `backend/tools/rag_tool.py` | Semantic search over internal docs (ChromaDB). Top-5 chunks. |
| `web_search` | `backend/tools/search_tool.py` | Live web search via Tavily. Max 5 results. |
| `python_executor` | `backend/tools/python_tool.py` | Python in isolated subprocess (30s timeout). Captures matplotlib charts automatically. |
| `purchase_order_action` | `backend/tools/purchase_order_tool.py` | Manage supplier POs: `list_suppliers`, `create_po`, `approve_po`, `receive_po`, `get_po`, `list_pos`. **Blocked at code level unless user has PO intent + approval for write actions.** |

The agent chains tools as needed — e.g. `query_library` → `python_executor` for common DB data with charts.

### Query Library

44+ pre-built queries in `backend/queries/library.py`, organised by category:

| Category | Query names |
|---|---|
| Sales/Revenue | `total_revenue`, `revenue_by_month`, `revenue_by_category`, `sales_last_7d`, `sales_last_30d`, `sales_last_90d`, `aov_by_month`, `revenue_share_by_category`, `revenue_by_category_30d`, `revenue_by_category_90d` |
| Products | `top_products_by_revenue`, `top_products_by_quantity`, `products_by_category`, `top_rated_products`, `products_without_reviews`, `top_products_with_share`, `high_rated_low_sales` |
| Inventory | `low_stock`, `out_of_stock`, `inventory_overview`, `stockout_risk` |
| Orders | `orders_by_status`, `recent_orders`, `orders_today`, `pending_orders`, `cancelled_order_rate` |
| Customers | `top_customers_by_spend`, `new_customers_this_month`, `customer_count`, `customers_with_most_orders`, `customer_segments` |
| Reviews | `rating_distribution`, `recent_reviews`, `worst_rated_products` |
| API Usage | `api_usage_last_30_days`, `api_usage_summary` |
| Suppliers & POs | `suppliers`, `purchase_orders`, `sales_velocity`, `replenishment_candidates`, `reorder_with_cost` |
| Prospecting | `business_health_snapshot`, `opportunity_matrix`, `automation_candidates` |

**Analytical queries added (9 new):** `sales_last_30d` (30d summary with period-over-period comparison), `aov_by_month` (AOV trend), `revenue_share_by_category` (% share), `top_products_with_share` (top 15 with % share), `stockout_risk` (< 14 days cover), `high_rated_low_sales` (hidden gems), `customer_segments` (VIP/Regular/Occasional/New tiers), `cancelled_order_rate` (monthly %), `reorder_with_cost` (suggested qty + PO line costs).

To add a new query: add an entry to `QUERY_LIBRARY` in `backend/queries/library.py` — no other files need changes.

## Database Schema

The SQLite database (`dev.db` at repo root) uses Prisma-generated **camelCase columns**.

**Critical SQL rules:**
- `Order` is a reserved word — ALWAYS quote it: `SELECT * FROM "Order"`
- Column names are camelCase: `firstName`, `customerId`, `orderDate`, etc.
- Only `SELECT` queries are permitted (enforced at PRAGMA level and application level) — except `purchase_order_action` which writes POs/inventory
- Never SELECT `id` columns in results — they are UUIDs, not useful to users
- Never expose internal IDs, UUIDs, or SKUs in customer-facing content (emails, messages)

**Tables:**

| Table | Columns |
|-------|---------|
| `Customer` | id, firstName, lastName, email, phone, createdAt |
| `Product` | id, name, description, price, category, sku |
| `"Order"` | id, customerId, orderDate, status, totalAmount |
| `OrderItem` | id, orderId, productId, quantity, unitPrice |
| `Inventory` | id, productId, stockLevel, lastRestock |
| `Review` | id, productId, customerId, rating, comment, createdAt |
| `ApiUsage` | id, date, requestCount, totalTokens |
| `Supplier` | id, name, email, phone, createdAt |
| `PurchaseOrder` | id, supplierId, createdAt, status, totalAmount |
| `PurchaseOrderItem` | id, purchaseOrderId, productId (nullable), sku, name, quantity, unitCost |
| `Conversation` | id, title, createdAt, updatedAt |
| `Message` | id, conversationId, role, content, createdAt |

Order status values: `'Pending'` | `'Shipped'` | `'Delivered'` | `'Cancelled'`

PurchaseOrder status values: `'Draft'` | `'Approved'` | `'Sent'` | `'Received'` | `'Cancelled'`

**Relationships:**
- `PurchaseOrder.supplierId` → `Supplier.id`
- `PurchaseOrderItem.purchaseOrderId` → `PurchaseOrder.id`
- `PurchaseOrderItem.productId` → `Product.id` (nullable — allows ordering new products not yet in catalog)

**Seed data:** 60 customers, 240 products (12 categories), 80 orders, ~800 reviews, 1 supplier (EcoSource Trading), 30 API usage records.

**Note:** `db.py` uses `dict_factory` so all `fetchone()` / `fetchall()` results are dicts — always use named keys (e.g. `row["cnt"]`), never positional indexes. WAL mode and 30s timeout are enabled to prevent database lock errors.

## RAG Knowledge Base

10 Markdown documents in `docs/` covering:
- Product categories guide, technical glossary, comparison guide
- Order & shipping policies, return policy
- Customer FAQ, user profile & buying guide
- Reviews & rating policy
- Promotions, bundles & discounts
- AI assistant manual
- Trends & analytics report

Run `python -m rag.ingest` from `agent/` after adding or modifying docs. Chunk size: 800 chars, overlap: 100, top-k: 5.

## Key Configuration (`backend/config.py`)

| Variable | Default | Purpose |
|---|---|---|
| `LLM_MODEL` | `gpt-4o-mini-2024-07-18` | OpenAI chat model |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `EXECUTOR_TIMEOUT_SEC` | `30` | Python executor subprocess timeout |
| `RAG_TOP_K` | `5` | Number of RAG chunks returned |
| `DB_PATH` | `../dev.db` | SQLite database path (relative to `agent/`) |
| `CHROMA_DIR` | `agent/chroma_db/` | ChromaDB persistence directory |
| `CHARTS_DIR` | `backend/charts/` | Directory for saved chart PNGs |
| `BACKEND_BASE_URL` | `http://127.0.0.1:8001` | Used by python_tool to build chart URLs |
| `USE_LEGACY_AGENT` | `False` | Set `True` to fall back to the old create_react_agent implementation |
| `BACKEND_URL` | `http://localhost:8001` | Frontend → backend base URL (in `src/lib/backend.ts`) |

## Frontend Notes

- **Tailwind CSS v4**: Uses `@import "tailwindcss"` and `@plugin` in `globals.css`. The `tailwind.config.ts` file is effectively ignored — all plugin loading goes through `@plugin "@tailwindcss/typography"` in CSS.
- **Vercel AI SDK `useChat`**: The Next.js API route at `src/app/api/chat/route.ts` bridges `useChat` requests to FastAPI SSE, converting `token`/`done`/`error`/`perf` events into Vercel AI SDK data stream format. `maxDuration = 120` and `AbortController` with 120s timeout.
- **JSON block extraction**: `MessageBubble` runs `extractStructuredBlocks()` (from `src/lib/parsers.ts`) before SQL parsing to detect `USE_CASE_CARDS` and `HITL_REQUEST` JSON blocks. These are stripped from visible content and rendered as UI components. Extraction is skipped during streaming (`isStreaming` prop) to avoid parsing partial JSON.
- **Streaming approval placeholder**: During streaming, `MessageBubble` detects partial ` ```json ` blocks containing `HITL_REQUEST` and replaces them with an amber "Creating approval..." card with a spinner, instead of showing raw JSON.
- **SQL tab rendering**: `MessageBubble` runs `parseMessageContent()` on the cleaned content to find ` ```sql ``` + table` pairs. These are rendered as `SqlResultsBlock` (tabbed: Results / SQL Query). Standalone tables without SQL get a simpler `Results` card.
- **Approval rendering**: `HitlApproval` component renders **outside the message bubble** as a full-width card. Two-column layout: evidence/preview on the left, controls on the right. Amber gradient header with risk tags. Evidence section is **expanded by default** (`useState(true)`). "On approve" and "On reject" info lines are rendered above the action bar when present in the HITL payload. Actions dispatch `[HITL Response]` user messages via `ConversationClient.handleHitlAction()`.
- **Approval Response messages**: User messages starting with `[HITL Response]` are rendered as a friendly bubble (checkmark + "Approved" or X + "Rejected") via `HitlResponseBubble` in `MessageBubble.tsx` — the raw JSON/control data is hidden from the user. `handleHitlAction` submits directly via `append()` without setting the input field.
- **Use Cases Drawer**: `UseCasesDrawer` component with 5 tabs (SQL, RAG, WEB, Charts, Approval). Falls back to hardcoded default cards when no LLM-provided data exists. Opened via "Browse All Use Cases" button or the grid icon in `ChatInput`. Internal IDs use `"HITL"` but display text shows `"Approval"` via `BADGE_LABELS` mapping.
- **Chart rendering**: `MessageBubble` overrides the `img` ReactMarkdown component to render charts with rounded border styling.
- **Prose color overrides**: Assistant message bubbles use explicit `prose-*` color overrides with CSS variables (`var(--foreground)`, `var(--accent)`) to prevent Tailwind Typography defaults (blue/gray) from overriding the app theme.
- **Copy buttons**: Both user and assistant message bubbles show a copy button on hover, positioned at `top-3 right-3` for both.
- **Sidebar navigation**: 3-tab nav (Chat, Database, Documents) above the conversations list. Conversations list only visible on the Chat tab.
- **Sidebar refresh**: Custom DOM event `aria:conversation-updated` dispatched from `ConversationClient.onFinish`. Two dispatches: immediate + 3s delay (to pick up auto-generated title).
- **Auto-title**: Backend generates a title after the first exchange using `ChatOpenAI`. Runs as a background task after the SSE stream completes.
- **Theme**: Light/dark mode via `next-themes`. CSS custom properties (`var(--foreground)`, `var(--accent)`, etc.) defined in `globals.css`.

## Known Issues & Fixes

### Complex Queries Produce No Response (Agent Infinite Tool Loop)

**Problem:** When the user asks a complex, multi-step question (e.g., "Create a 30-day promotion strategy", "Analyze sales and identify opportunities", "Prepare a purchase order"), the agent produces **no response** — the UI shows a loading state indefinitely. Simple questions (e.g., "top 5 products") work fine.

**Root Cause:** `gpt-4o-mini` gets stuck in an **infinite tool-calling loop** for complex queries. It keeps calling `query_library`, `sql_query`, `python_executor` over and over, gathering more data, but **never decides to stop and produce a final text answer**. The `stream_agent` function in `agent.py` only yields text from `on_chat_model_stream` events — during tool-call steps, the LLM produces `tool_call_chunks` (not text), so zero tokens reach the user. The SSE connection eventually times out or hangs.

**Contributing factors:**
1. **No tool call limit** — the agent could make unlimited tool calls without ever responding
2. **No heartbeat during tool execution** — long silent periods (30-60+ seconds) caused the browser/proxy to drop the SSE connection
3. **No `maxDuration` on the Next.js API route** (`src/app/api/chat/route.ts`) — default Next.js timeout killed long-running requests
4. **No overall timeout on the agent** — a stuck ReAct loop could hang indefinitely
5. **No error logging** — failures in the agent loop were swallowed silently

**Fix applied — Explicit StateGraph (replaces black-box ReAct agent):**

- **`backend/graph/`** — New StateGraph implementation:
  - **Structural tool limit**: Conditional edge in `edges.py` routes to `force_respond` when `tool_call_count >= max_tool_calls`. Graph physically cannot loop past limit.
  - **force_respond node**: LLM without `bind_tools()` — physically cannot call tools. Uses SystemMessage (not HumanMessage) for the stop instruction.
  - **No orphaned tool calls**: Graph always completes to END. No patching needed.
  - **Native HITL interrupts**: `hitl_gate` node calls `interrupt()` — graph pauses. Resume via `Command(resume=decision)`. No global dicts.
  - **State-based PO intent/approval**: `po_intent` and `hitl_approved` live in graph state, passed to tools via augmented config. Thread-safe by design.
  - **Per-thread asyncio locks**: Prevent concurrent requests from corrupting checkpoints.
  - **Response-mode classifier** (`mode_classifier.py`): Unchanged — classifies each message and sets `max_tokens`/`max_tool_calls`.
  - **Heartbeat mechanism**: Every 5 seconds of silence, empty token keeps SSE alive.
  - **90-second overall timeout**: Agent run capped; produces user-friendly warning if exceeded.
  - **`recursion_limit=25`** in runtime config.

- **`backend/agent.py`** — Thin facade:
  - Delegates to `backend/graph/` (StateGraph) or `backend/agent_legacy.py` based on `USE_LEGACY_AGENT` flag in `config.py`.

- **`backend/agent_legacy.py`** — Legacy fallback:
  - Original `create_react_agent` implementation preserved for rollback. Set `USE_LEGACY_AGENT=True` in `config.py` to activate.

- **`backend/validators.py`** — Post-processing validation:
  - **Summary/breakdown coherence**: Detects if a stated dollar total deviates >10% from the table breakdown
  - **HITL structure validation**: Checks HITL_REQUEST JSON for required fields, non-empty evidence, valid artifacts
  - **Response length monitoring**: Logs warnings when responses exceed mode-specific length limits

- **`src/app/api/chat/route.ts`** — Frontend proxy:
  - **`maxDuration = 120`** export to allow long-running requests (raised from 60)
  - **`AbortController` with 120s timeout** on the backend fetch
  - Empty heartbeat tokens are silently skipped

- **`backend/routers/chat.py`** — Post-processing:
  - Runs `check_summary_breakdown_coherence()` and `validate_hitl_structure()` after response assembly
  - Appends coherence footnotes if mismatch detected
  - Logs HITL validation warnings

- **`backend/core/system_prompt.py`** — 3-tier prompt architecture:
  - Core prompt reduced to ~500 tokens (identity, 6 rules, output discipline, self-check)
  - Response templates, HITL contracts, chart standards, prospecting mode, schema, tool guide → moved out
  - **`backend/core/mode_templates.py`** (new) — Per-mode injection templates (factual/analytical/chart/hitl/rag/prospecting). Only the matching mode's template is sent per request.
  - **Tool docstrings enriched** — Database schema → `sql_tool.py`, query names → `query_library.py`, RAG rules → `rag_tool.py`, chart standards → `python_tool.py`, web rules → `search_tool.py`
  - **`backend/graph/nodes.py`** — `_build_system_prompt(state)` helper reads `state["mode"]` and appends the matching template. Used by all 3 preprocess functions.
  - Net result: ~550–1,235 tokens per request vs ~5,200 before (~70% reduction)

- **`backend/tools/python_tool.py`** — Chart insight hint:
  - After chart generation, appends instruction: "write exactly 1 INSIGHT line and 1 ACTION line, then stop"

**How to verify:** Restart the backend, ask a complex question like "Create a 30-day promotion strategy to increase revenue based on our sales data." Watch the backend terminal — you should see mode classification and numbered tool calls logged. Verify: (1) response completes without timeout, (2) response is shorter than before, (3) HITL_REQUEST has required fields.

**If the problem persists:** Adjust `max_tokens` per mode in `backend/mode_classifier.py`, or the `_STOP_TOOLS_MSG` in `backend/graph/nodes.py`.

### Streaming Architecture Note

LLM-calling nodes in `backend/graph/nodes.py` **must** be Runnable chains (`RunnableLambda | ChatOpenAI | RunnableLambda`), not function nodes that call `llm.ainvoke()`. This is required for `astream_events(version="v2")` to capture individual tokens via `on_chat_model_stream` events. Direct `llm.ainvoke()` calls inside function nodes are opaque to `astream_events` and produce zero streaming tokens. The three Runnable chain nodes are: `plan_and_call`, `force_respond`, and `post_approve`.

## Performance Optimizations

The following optimizations have been implemented across the codebase:

### Direct Query Routing (Fast Lane)

Simple factual questions (e.g. "total revenue", "top products", "low stock") are matched against 23 regex patterns in `mode_classifier.py` (`_DIRECT_ROUTES`) and routed directly to `query_library` without any LLM call. Only matches short messages (< 80 chars, no complex connectors). Classified as `mode="direct_query"` → `direct_query` node → END.

### Greeting Fast Lane

Greetings (hello, hi, hey, thanks, who are you, etc.) are matched via `_GREETING_PATTERN` regex in `mode_classifier.py` and handled by `fast_response` node with canned responses — no LLM call at all.

### Conversation Summarization

When conversations exceed 12 messages, the `summarize_if_needed` node condenses older messages into a summary (keeping the last 6 verbatim). Uses a dedicated `_llm_summarizer` instance (`gpt-4o-mini`, 300 max_tokens, 30s timeout). The summary is stored in `AriaState.summary` and prepended as a SystemMessage.

### Result Caching

Both `sql_tool.py` and `query_library.py` implement in-memory caches with 60-second TTL. Cache keys are based on lowercased query text (sql_tool) or query name (query_library). Reduces database load for repeated queries.

### Async SQLite (aiosqlite)

`sql_tool.py` and `query_library.py` use `aiosqlite` for true async database access instead of blocking `sqlite3` calls. Enables non-blocking tool execution within the async graph.

### LLM Fallback Chains

All LLM instances in `nodes.py` use `.with_fallbacks()` (primary: `gpt-4o-mini-2024-07-18`, fallback: `gpt-4o-mini`) and `.with_retry(stop_after_attempt=2)` for resilience.

### Prompt Prefix Caching

The core system prompt is sent as a separate SystemMessage (always identical) followed by a mode-specific template SystemMessage. This split enables OpenAI's prompt prefix caching on the core prompt across requests.

### Structured Logging

`structlog` is configured in `main.py` with contextvars, ISO timestamps, and console rendering. `RequestIdMiddleware` adds `X-Request-ID` headers and binds request context for tracing.

### Performance Event Tracking

`stream.py` tracks and emits performance metrics via `\x00PERF:` markers: TTFT, LLM thinking time, per-tool execution time, and total graph duration. These are forwarded as `perf` SSE events through the Next.js proxy to the frontend. Tool status emoji messages (e.g. "Querying database...") are injected on tool start and stripped before message persistence.

### Benchmark Suite

`backend/tests/benchmark_results.json` contains results from a 10-scenario benchmark covering: baseline (no tools), SQL library, raw SQL, RAG, web search, charts, multi-tool, HITL flow, and complex multi-step queries. Key metrics: avg TTFT, avg tool time, avg LLM time, avg graph duration, per-scenario breakdown.

## Common Tasks for Claude Code

- **Test the app**: Start both servers, then use Playwright MCP to navigate to `http://localhost:3000`
- **Add a pre-built query**: Add an entry to `QUERY_LIBRARY` in `backend/queries/library.py` — no other files need changes
- **Add a new tool**: Create in `backend/tools/`, import in `backend/tools/__init__.py`, add to `ALL_TOOLS` list. Put usage instructions in the tool's docstring (not system_prompt.py). If the tool is mode-specific, add a template entry in `backend/core/mode_templates.py`.
- **Add RAG docs**: Place `.md` files in `docs/`, then run `python -m rag.ingest` from `agent/`
- **Switch to legacy agent**: Set `USE_LEGACY_AGENT = True` in `backend/config.py`
- **Change the LLM**: Update `LLM_MODEL` in `backend/config.py`
- **Add a new API route (backend)**: Create router in `backend/routers/`, register in `backend/main.py`
- **Add a new page (frontend)**: Create under `src/app/`, add layout using `<AppShell>`, add nav tab in `Sidebar.tsx`
- **Change backend port**: Update `BACKEND_BASE_URL` in `backend/config.py` AND the default in `src/lib/backend.ts`
- **Add an approval use case**: Define controls + triggers in the `hitl` template in `backend/core/mode_templates.py`, add a card to `UseCasesDrawer.tsx` defaults, add to `ChatArea.tsx` front actions if replacing one
- **Add a supplier**: Insert into `Supplier` table (or add to `prisma/seed.ts` for full reseeds)
- **Modify system prompt rules**: Edit `backend/core/system_prompt.py` for core rules, or `backend/core/mode_templates.py` for per-mode templates
- **Tune response mode**: Edit `backend/mode_classifier.py` — adjust `max_tokens`, `max_tool_calls`, or keyword patterns per mode
- **Add a validator**: Add a function to `backend/validators.py`, call it in `backend/routers/chat.py` after response assembly
- **Run eval harness**: `"agent/.venv/Scripts/python.exe" backend/tests/eval_prompts.py` — sends 23 test prompts to the running backend. Checks: required/forbidden strings, length ceilings, timeout tracking. Reports PASS/WARN/FAIL. Backend must be running.
- **Add an eval test**: Add entries to the `TESTS` list in `backend/tests/eval_prompts.py` with `name`, `prompt`, `required`, `required_any`, `forbidden`, and optionally `max_response_length`
- **Add a direct query route**: Add a `(regex, query_name)` tuple to `_DIRECT_ROUTES` in `backend/mode_classifier.py` — matched queries skip LLM entirely

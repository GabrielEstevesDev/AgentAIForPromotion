# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Aria** is a full-stack AI-powered e-commerce assistant designed as a demo-ready product for potential clients. It consists of:

- **Frontend**: Next.js 15 (App Router) with React 19, Tailwind CSS 4, and the Vercel AI SDK (`useChat` hook). Runs on port **3000**.
- **Backend**: FastAPI with SSE streaming, wrapping a **LangGraph ReAct agent** backed by `gpt-4o-mini`. Runs on port **8001**.

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
        HitlApproval.tsx      — Full-width approval card (2-column layout, amber gradient header, controls + evidence)
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
    main.py                   — FastAPI app, CORS, lifespan (builds agent)
    agent.py                  — build_agent() + stream_agent() with SQL injection + approval detection + PO intent tracking
    config.py                 — All settings (LLM_MODEL, DB_PATH, CHARTS_DIR, etc.)
    db.py                     — SQLite connection with dict_factory, WAL mode, 30s timeout
    hitl_state.py             — Per-thread approval tracking + PO intent tracking (code-level enforcement)
    core/
      system_prompt.py        — Aria's system prompt (3 top rules, tool rules, SQL schema, approval contracts)
    routers/
      chat.py                 — POST /api/chat — SSE streaming endpoint
      conversations.py        — CRUD endpoints for conversations + messages
      charts.py               — GET /api/charts/{filename} — serves chart PNG files
      purchase_orders.py      — Supplier PO CRUD + approve/receive with inventory updates
      database_explorer.py    — GET /api/database/tables — browse DB tables with pagination
      documents.py            — GET /api/documents — serve RAG docs as markdown + PDF (fpdf2)
    tools/
      query_library.py        — Pre-built SQL query lookup by name (29 queries)
      sql_tool.py             — Read-only SQL SELECT; returns results as markdown table
      rag_tool.py             — Delegates to rag/retriever.py (ChromaDB)
      search_tool.py          — Tavily web search (max 5 results)
      python_tool.py          — Python subprocess executor; captures matplotlib charts as PNG
      purchase_order_tool.py  — LangGraph tool for managing supplier POs (create/approve/receive) with code-level intent guard + approval guard
    queries/
      library.py              — Dict of 29 named pre-built SQL queries (add entries here to expand)
    rag/
      ingest.py               — Chunks docs/*.md → ChromaDB (safe to re-run)
      retriever.py            — lru_cache Chroma vectorstore singleton
    charts/                   — Saved chart PNGs (auto-cleaned after 1h)
    chroma_db/                — Persisted ChromaDB vectorstore (auto-generated)

  agent/                      — Original standalone agent (Gradio UI + CLI)
    .venv/                    — Python virtual environment (used by backend too)
    app.py                    — Gradio web UI (port 7860) — legacy standalone mode
    main.py                   — CLI REPL (/exit, /reset, /tools) — legacy
    requirements.txt          — Python dependencies (includes matplotlib)

  docs/                       — RAG knowledge base (10 Markdown files)
  dev.db                      — SQLite database (Prisma-generated schema)
  prisma/                     — Prisma schema (used for migrations only)
  guidelines.md               — Product guidelines (USE_CASE_CARDS, HITL, output style)
```

### Request Flow

1. User types a message in the browser (`ConversationClient`)
2. If no conversation exists yet, a new one is created via `POST /api/conversations`
3. `useChat` sends a request to Next.js route `/api/chat/route.ts`
4. The Next.js route proxies to `POST http://127.0.0.1:8001/api/chat` and bridges the FastAPI SSE stream into the Vercel AI SDK data stream format (`0:` text tokens, `d:` done)
5. FastAPI's `stream_agent` runs the LangGraph ReAct loop:
   - Detects approval messages and sets the per-thread approval flag
   - Tracks PO intent from user keywords (purchase order, replenish, restock, etc.)
   - Listens for `on_tool_end` events from `sql_query` / `query_library` and captures the SQL
   - Injects a ` ```sql ` block before the first response token (so the SQL always appears)
   - Streams the LLM's final answer token by token
6. After streaming completes, messages are persisted to SQLite. Auto-title is generated for the first exchange.
7. `onFinish` in `useChat` fires `aria:conversation-updated` DOM events to refresh the sidebar

### SQL Query Tab Feature

When the agent uses `sql_query`, the response content is automatically prefixed with the SQL in a ` ```sql ` fenced block (injected in `agent.py`, not by the LLM). `MessageBubble` parses the content and detects ` ```sql ``` + markdown table` pairs, rendering them as a unified `SqlResultsBlock` component with:
- **Results tab** (default) — styled table with "Copy CSV" button
- **SQL Query tab** — exact SQL with "Copy SQL" button

The SQL injection happens at the streaming layer (`stream_agent` in `agent.py`) via `on_tool_end` events, making it 100% reliable regardless of LLM behavior.

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
1. **Approval guard** (`backend/hitl_state.py` + `purchase_order_tool.py`): `stream_agent` detects `[HITL Response]` approval messages and sets a per-thread flag. `purchase_order_action` tool blocks `create_po`/`approve_po`/`receive_po` unless the flag is set.
2. **PO intent guard** (`backend/agent.py` + `purchase_order_tool.py`): `stream_agent` scans user messages for PO-related keywords (purchase order, replenish, restock, etc.). `purchase_order_action` blocks ALL actions (even `list_suppliers`) unless the user has explicitly mentioned PO/replenishment. This prevents hallucinated PO workflows during unrelated tasks.
3. **System prompt rules** (`backend/core/system_prompt.py`): 3 prominent rules at the top — mandatory approval, stay on topic, PO only for replenishment. Plus anti-hallucination rules against casual positive responses triggering new tasks.

**3 required approval use cases:**
- **Refund/Dispute Email** — RAG + SQL → email draft with tone/resolution controls. Email must include product names (not IDs) and total refund amount. After approval: final email + "email sending not configured" demo note.
- **30-Day Promotion Strategy** — SQL + charts → strategy with budget/discount controls
- **Replenishment + Purchase Order** — SQL + charts → PO draft with budget controls, auto-receives inventory on approval

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

**PO intent guard**: The `purchase_order_action` tool is completely blocked unless the user has explicitly mentioned PO/replenishment keywords in the conversation. This is enforced at code level in `purchase_order_tool.py` via `has_po_intent()` from `hitl_state.py`.

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

29 pre-built queries in `backend/queries/library.py`, organised by category:

| Category | Query names |
|---|---|
| Sales/Revenue | `total_revenue`, `revenue_by_month`, `revenue_by_category` |
| Products | `top_products_by_revenue`, `top_products_by_quantity`, `products_by_category`, `top_rated_products`, `products_without_reviews` |
| Inventory | `low_stock`, `out_of_stock`, `inventory_overview` |
| Orders | `orders_by_status`, `recent_orders`, `orders_today`, `pending_orders` |
| Customers | `top_customers_by_spend`, `new_customers_this_month`, `customer_count`, `customers_with_most_orders` |
| Reviews | `rating_distribution`, `recent_reviews`, `worst_rated_products` |
| API Usage | `api_usage_last_30_days`, `api_usage_summary` |
| Suppliers & POs | `suppliers`, `purchase_orders`, `sales_velocity`, `replenishment_candidates` |

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
| `LLM_MODEL` | `gpt-4o-mini` | OpenAI chat model |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `EXECUTOR_TIMEOUT_SEC` | `30` | Python executor subprocess timeout |
| `RAG_TOP_K` | `5` | Number of RAG chunks returned |
| `DB_PATH` | `../dev.db` | SQLite database path (relative to `agent/`) |
| `CHROMA_DIR` | `agent/chroma_db/` | ChromaDB persistence directory |
| `CHARTS_DIR` | `backend/charts/` | Directory for saved chart PNGs |
| `BACKEND_BASE_URL` | `http://127.0.0.1:8001` | Used by python_tool to build chart URLs |
| `BACKEND_URL` | `http://localhost:8001` | Frontend → backend base URL (in `src/lib/backend.ts`) |

## Frontend Notes

- **Tailwind CSS v4**: Uses `@import "tailwindcss"` and `@plugin` in `globals.css`. The `tailwind.config.ts` file is effectively ignored — all plugin loading goes through `@plugin "@tailwindcss/typography"` in CSS.
- **Vercel AI SDK `useChat`**: The Next.js API route at `src/app/api/chat/route.ts` bridges `useChat` requests to FastAPI SSE, converting `token`/`done`/`error` events into Vercel AI SDK data stream format.
- **JSON block extraction**: `MessageBubble` runs `extractStructuredBlocks()` (from `src/lib/parsers.ts`) before SQL parsing to detect `USE_CASE_CARDS` and `HITL_REQUEST` JSON blocks. These are stripped from visible content and rendered as UI components. Extraction is skipped during streaming (`isStreaming` prop) to avoid parsing partial JSON.
- **Streaming approval placeholder**: During streaming, `MessageBubble` detects partial ` ```json ` blocks containing `HITL_REQUEST` and replaces them with an amber "Creating approval..." card with a spinner, instead of showing raw JSON.
- **SQL tab rendering**: `MessageBubble` runs `parseMessageContent()` on the cleaned content to find ` ```sql ``` + table` pairs. These are rendered as `SqlResultsBlock` (tabbed: Results / SQL Query). Standalone tables without SQL get a simpler `Results` card.
- **Approval rendering**: `HitlApproval` component renders **outside the message bubble** as a full-width card. Two-column layout: evidence/preview on the left, controls on the right. Amber gradient header with risk tags. Actions dispatch `[HITL Response]` user messages via `ConversationClient.handleHitlAction()`.
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

**Fix applied (files changed):**

- **`backend/agent.py`** — Core fix:
  - **Tool call counter + forced response (`_MAX_TOOL_CALLS = 10`)**: After 10 tool calls without producing text, `_run_with_retry()` detects the agent is stuck and calls `_force_final_response()`, which sends a follow-up message with `recursion_limit=4` forcing the LLM to answer with the data it already has
  - **Heartbeat mechanism**: Every 8 seconds of silence, an empty token is yielded to keep the SSE connection alive
  - **90-second overall timeout**: Agent run is capped; produces a user-friendly warning if exceeded
  - **`timeout=60`** on `ChatOpenAI` to prevent individual OpenAI API calls from hanging
  - **`recursion_limit=25`** in the runtime config to prevent runaway loops
  - **Console logging**: Every tool call is logged with name and input for debugging

- **`src/app/api/chat/route.ts`** — Frontend proxy:
  - **`maxDuration = 180`** export to allow long-running requests
  - **`AbortController` with 180s timeout** on the backend fetch
  - Empty heartbeat tokens are silently skipped (not written to the Vercel AI SDK data stream)

- **`backend/routers/chat.py`** — Error handling:
  - Error logging with conversation ID
  - User-friendly messages for recursion limit and timeout errors

- **`backend/main.py`** — Observability:
  - `logging.basicConfig()` configured so agent errors appear in the terminal

**How to verify:** Restart the backend, ask a complex question like "Create a 30-day promotion strategy to increase revenue based on our sales data." Watch the backend terminal — you should see numbered tool calls logged. After at most 10 tool calls, the agent should produce a text response.

**If the problem persists:** The `_MAX_TOOL_CALLS` limit (currently 10) or the `_STOP_TOOLS_MSG` in `backend/agent.py` may need tuning. Consider upgrading from `gpt-4o-mini` to `gpt-4o` in `backend/config.py` — larger models are better at deciding when to stop calling tools.

## Common Tasks for Claude Code

- **Test the app**: Start both servers, then use Playwright MCP to navigate to `http://localhost:3000`
- **Add a pre-built query**: Add an entry to `QUERY_LIBRARY` in `backend/queries/library.py` — no other files need changes
- **Add a new tool**: Create in `backend/tools/`, import in `backend/tools/__init__.py`, add to `ALL_TOOLS` list, document in `backend/core/system_prompt.py`
- **Add RAG docs**: Place `.md` files in `docs/`, then run `python -m rag.ingest` from `agent/`
- **Change the LLM**: Update `LLM_MODEL` in `backend/config.py`
- **Add a new API route (backend)**: Create router in `backend/routers/`, register in `backend/main.py`
- **Add a new page (frontend)**: Create under `src/app/`, add layout using `<AppShell>`, add nav tab in `Sidebar.tsx`
- **Change backend port**: Update `BACKEND_BASE_URL` in `backend/config.py` AND the default in `src/lib/backend.ts`
- **Add an approval use case**: Define controls + triggers in `backend/core/system_prompt.py`, add a card to `UseCasesDrawer.tsx` defaults, add to `ChatArea.tsx` front actions if replacing one
- **Add a supplier**: Insert into `Supplier` table (or add to `prisma/seed.ts` for full reseeds)
- **Modify system prompt rules**: Edit `backend/core/system_prompt.py` — the 3 top rules (mandatory approval, stay on topic, PO scope) are critical for preventing agent hallucinations

"use client";

import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, Check, CheckCircle, Copy, Database, Loader2, ShieldCheck, Table2, User, XCircle, MessageSquare } from "lucide-react";

import type { ChatMessage, TraceEvent } from "@/lib/api";
import type { HitlRequestPayload, UseCaseCardsPayload } from "@/lib/types";
import { extractStructuredBlocks } from "@/lib/parsers";
import { HitlApproval } from "./HitlApproval";

// ---------------------------------------------------------------------------
// Content parsing — detect ```sql block + following markdown table pairs
// ---------------------------------------------------------------------------

type Segment =
  | { type: "markdown"; content: string }
  | { type: "sql-results"; sql: string; tableMarkdown: string }
  | { type: "hitl-request"; payload: HitlRequestPayload }
  | { type: "approval-creating" };

function extractLeadingTable(
  text: string,
): { table: string; consumed: number; preText: string } | null {
  const lines = text.split("\n");
  let tableStart = -1;

  // Find first | line within the next ~8 lines (skipping blank lines / intro text)
  for (let i = 0; i < Math.min(lines.length, 8); i++) {
    if (lines[i].trim().startsWith("|")) {
      tableStart = i;
      break;
    }
  }
  if (tableStart === -1) return null;

  // Collect consecutive | lines
  const tableLines: string[] = [];
  let i = tableStart;
  for (; i < lines.length; i++) {
    const t = lines[i].trim();
    if (t.startsWith("|")) {
      tableLines.push(lines[i]);
    } else if (t === "" && tableLines.length > 0) {
      i++;
      break;
    } else {
      break;
    }
  }

  if (tableLines.length < 2) return null;
  const tableMarkdown = tableLines.join("\n");
  if (!tableMarkdown.includes("---")) return null; // must have separator row

  const consumedText = lines.slice(0, i).join("\n");
  const consumed = consumedText.length + (i < lines.length ? 1 : 0);

  // Preserve any meaningful content between the SQL block and the table start
  // (e.g. chart image tags, intro text) so it doesn't get swallowed
  const preText = lines.slice(0, tableStart).join("\n").trim();

  return { table: tableMarkdown, consumed, preText };
}

function parseMessageContent(content: string): Segment[] {
  const result: Segment[] = [];
  const sqlBlockRegex = /```sql\n([\s\S]*?)```/g;
  let cursor = 0;

  for (const match of content.matchAll(sqlBlockRegex)) {
    const matchStart = match.index!;
    const matchEnd = matchStart + match[0].length;
    const sql = match[1].trim();

    const before = content.slice(cursor, matchStart);
    if (before.trim()) result.push({ type: "markdown", content: before });

    const afterBlock = content.slice(matchEnd);
    const tableResult = extractLeadingTable(afterBlock);

    if (tableResult) {
      // Emit any content between the SQL block and the table (e.g. chart images, intro text)
      if (tableResult.preText) {
        result.push({ type: "markdown", content: tableResult.preText });
      }
      result.push({ type: "sql-results", sql, tableMarkdown: tableResult.table });
      cursor = matchEnd + tableResult.consumed;
    } else {
      result.push({ type: "markdown", content: match[0] });
      cursor = matchEnd;
    }
  }

  const remaining = content.slice(cursor);
  if (remaining.trim()) result.push({ type: "markdown", content: remaining });

  return result;
}

// ---------------------------------------------------------------------------
// Shared table cell styles (used both in SqlResultsBlock and standalone tables)
// ---------------------------------------------------------------------------

const TABLE_COMPONENTS = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  table: ({ children }: any) => (
    <table className="w-full border-collapse text-sm">{children}</table>
  ),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  th: ({ children }: any) => (
    <th className="border-b border-[var(--border)] bg-[color:color-mix(in_srgb,var(--accent)_8%,transparent)] px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">
      {children}
    </th>
  ),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  tr: ({ children }: any) => (
    <tr className="border-b border-[var(--border)] transition-colors last:border-0 hover:bg-[color:color-mix(in_srgb,var(--foreground)_3%,transparent)]">
      {children}
    </tr>
  ),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  td: ({ children }: any) => (
    <td className="px-4 py-2.5 text-sm text-[var(--foreground)]">{children}</td>
  ),
};

// ---------------------------------------------------------------------------
// SqlResultsBlock — unified tabbed SQL / Results block
// ---------------------------------------------------------------------------

function SqlResultsBlock({ sql, tableMarkdown }: { sql: string; tableMarkdown: string }) {
  const [tab, setTab] = useState<"results" | "sql">("results");
  const [copiedSql, setCopiedSql] = useState(false);
  const [copiedCsv, setCopiedCsv] = useState(false);
  const tableContainerRef = useRef<HTMLDivElement>(null);

  async function handleCopySql() {
    await navigator.clipboard.writeText(sql);
    setCopiedSql(true);
    setTimeout(() => setCopiedSql(false), 2000);
  }

  async function handleCopyCsv() {
    const container = tableContainerRef.current;
    if (!container) return;
    const rows = Array.from(container.querySelectorAll("tr"));
    const csv = rows
      .map((row) =>
        Array.from(row.querySelectorAll("th, td"))
          .map((cell) => `"${(cell.textContent ?? "").replace(/"/g, '""')}"`)
          .join(","),
      )
      .join("\n");
    await navigator.clipboard.writeText(csv);
    setCopiedCsv(true);
    setTimeout(() => setCopiedCsv(false), 2000);
  }

  return (
    <div className="not-prose my-4 overflow-hidden rounded-2xl border border-[var(--border)]">
      {/* Tab bar */}
      <div className="flex items-center bg-[color:color-mix(in_srgb,var(--foreground)_4%,transparent)]">
        <button
          type="button"
          onClick={() => setTab("results")}
          className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs font-semibold transition ${
            tab === "results"
              ? "border-[var(--accent)] text-[var(--accent)]"
              : "border-transparent text-[var(--muted)] hover:text-[var(--foreground)]"
          }`}
        >
          <Table2 size={13} />
          Results
        </button>
        <button
          type="button"
          onClick={() => setTab("sql")}
          className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs font-semibold transition ${
            tab === "sql"
              ? "border-[var(--accent)] text-[var(--accent)]"
              : "border-transparent text-[var(--muted)] hover:text-[var(--foreground)]"
          }`}
        >
          <Database size={13} />
          SQL Query
        </button>

        {/* Copy button — right side */}
        <div className="ml-auto pr-2">
          {tab === "results" ? (
            <button
              type="button"
              onClick={handleCopyCsv}
              className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-[var(--muted)] transition hover:bg-[color:color-mix(in_srgb,var(--foreground)_8%,transparent)] hover:text-[var(--foreground)]"
            >
              {copiedCsv ? <Check size={11} /> : <Copy size={11} />}
              {copiedCsv ? "Copied!" : "Copy CSV"}
            </button>
          ) : (
            <button
              type="button"
              onClick={handleCopySql}
              className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-[var(--muted)] transition hover:bg-[color:color-mix(in_srgb,var(--foreground)_8%,transparent)] hover:text-[var(--foreground)]"
            >
              {copiedSql ? <Check size={11} /> : <Copy size={11} />}
              {copiedSql ? "Copied!" : "Copy SQL"}
            </button>
          )}
        </div>
      </div>

      {/* Border under tab bar */}
      <div className="border-b border-[var(--border)]" />

      {/* Tab content */}
      {tab === "results" ? (
        <div ref={tableContainerRef} className="overflow-x-auto">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={TABLE_COMPONENTS}>
            {tableMarkdown}
          </ReactMarkdown>
        </div>
      ) : (
        <pre className="m-0 overflow-x-auto bg-black/15 px-5 py-4 font-mono text-xs leading-relaxed text-[var(--foreground)]">
          <code>{sql}</code>
        </pre>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Markdown components for regular (non-sql-table) content
// ---------------------------------------------------------------------------

const MARKDOWN_COMPONENTS = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  code: ({ className, children }: any) => (
    <code className="rounded-md bg-black/10 px-1.5 py-0.5 font-mono text-[0.9em]">
      {children}
    </code>
  ),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  pre: ({ children }: any) => (
    <pre className="overflow-x-auto rounded-2xl bg-black/10 p-4 font-mono text-sm">
      {children}
    </pre>
  ),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  img: ({ src, alt }: any) => (
    <img
      src={src}
      alt={alt ?? "chart"}
      loading="eager"
      key={src}
      className="my-3 max-w-full rounded-2xl border border-[var(--border)] shadow-md"
    />
  ),
  // Standalone tables (no SQL block before them) — simple Results card
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  table: ({ children }: any) => (
    <div className="not-prose my-4 overflow-hidden rounded-2xl border border-[var(--border)]">
      <div className="flex items-center gap-2 border-b border-[var(--border)] bg-[color:color-mix(in_srgb,var(--foreground)_4%,transparent)] px-3 py-2.5">
        <Table2 size={13} className="text-[var(--accent)]" />
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
          Results
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">{children}</table>
      </div>
    </div>
  ),
  th: TABLE_COMPONENTS.th,
  tr: TABLE_COMPONENTS.tr,
  td: TABLE_COMPONENTS.td,
};

// ---------------------------------------------------------------------------
// HITL Response — friendly display for user approval/rejection messages
// ---------------------------------------------------------------------------

function parseHitlResponse(content: string): { action: string; notes?: string } | null {
  if (!content.startsWith("[HITL Response]")) return null;
  const actionMatch = content.match(/Action:\s*(\w+)/);
  const notesMatch = content.match(/Notes:\s*(.+)/);
  return {
    action: actionMatch?.[1] ?? "unknown",
    notes: notesMatch?.[1],
  };
}

function HitlResponseBubble({ action, notes }: { action: string; notes?: string }) {
  const isApprove = action === "approve";
  const isReject = action === "reject";
  const Icon = isApprove ? CheckCircle : isReject ? XCircle : MessageSquare;
  const label = isApprove ? "Approved" : isReject ? "Rejected" : `Response: ${action}`;

  return (
    <div className="flex items-center gap-2 text-white/90">
      <Icon size={16} />
      <span className="font-medium">{label}</span>
      {notes && <span className="text-white/70">— {notes}</span>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// MessageBubble
// ---------------------------------------------------------------------------

type MessageBubbleProps = {
  message: ChatMessage;
  onHitlAction?: (hitlId: string, actionId: string, controlValues: Record<string, unknown>, notes?: string) => void;
  onUseCaseCards?: (payload: UseCaseCardsPayload) => void;
  isStreaming?: boolean;
  resolvedHitlIds?: Set<string>;
};

export function MessageBubble({
  message,
  onHitlAction,
  onUseCaseCards,
  isStreaming,
  resolvedHitlIds,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const hitlResponse = isUser ? parseHitlResponse(message.content) : null;
  const [copied, setCopied] = useState(false);
  const useCaseCardsNotifiedRef = useRef(false);

  // Parse structured blocks (only for complete assistant messages)
  const { segments, regularSegments, hitlSegments, useCaseCards } = React.useMemo(() => {
    const empty = { segments: null, regularSegments: [] as Segment[], hitlSegments: [] as Segment[], useCaseCards: null };
    if (isUser) return empty;

    // Don't try to parse JSON during streaming — partial JSON will fail
    // Instead, detect HITL_REQUEST / USE_CASE_CARDS JSON blocks and show a placeholder
    if (isStreaming) {
      let streamContent = message.content;
      let showApprovalPlaceholder = false;

      // Detect ```json blocks containing HITL_REQUEST or USE_CASE_CARDS — strip them and show placeholder
      const jsonBlockMatch = streamContent.match(/```json[\s\S]*$/);
      if (jsonBlockMatch && jsonBlockMatch.index !== undefined) {
        const jsonFragment = jsonBlockMatch[0];
        if (jsonFragment.includes("HITL_REQUEST") || jsonFragment.includes("USE_CASE_CARDS")) {
          streamContent = streamContent.slice(0, jsonBlockMatch.index).trimEnd();
          if (jsonFragment.includes("HITL_REQUEST")) {
            showApprovalPlaceholder = true;
          }
        }
      }

      const segs = parseMessageContent(streamContent);
      if (showApprovalPlaceholder) {
        segs.push({ type: "approval-creating" });
      }
      return { segments: segs, regularSegments: segs, hitlSegments: [], useCaseCards: null };
    }

    const { useCaseCards: uc, hitlRequest, cleanContent } = extractStructuredBlocks(message.content);
    const segs = parseMessageContent(cleanContent);

    if (hitlRequest) {
      segs.push({ type: "hitl-request", payload: hitlRequest });
    }

    const regular = segs.filter((s) => s.type !== "hitl-request");
    const hitl = segs.filter((s) => s.type === "hitl-request");

    return { segments: segs, regularSegments: regular, hitlSegments: hitl, useCaseCards: uc };
  }, [isUser, isStreaming, message.content]);

  // Notify parent about USE_CASE_CARDS (once per message)
  useEffect(() => {
    if (useCaseCards && onUseCaseCards && !useCaseCardsNotifiedRef.current) {
      useCaseCardsNotifiedRef.current = true;
      onUseCaseCards(useCaseCards);
    }
  }, [useCaseCards, onUseCaseCards]);

  async function handleCopy() {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const hasRegularContent = isUser || !segments || regularSegments.length > 0;

  return (
    <article className={`group flex flex-col gap-2 ${isUser ? "items-end" : "items-start"}`}>
      {/* Message bubble — only rendered when there is non-HITL content */}
      {hasRegularContent && (
        <div className={`flex w-full gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
          {!isUser ? (
            <div className="mt-1 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent)]/15 text-[var(--accent)]">
              <Bot size={18} />
            </div>
          ) : null}

          <div
            className={`relative max-w-[min(52rem,100%)] rounded-[1.6rem] border px-5 py-4 shadow-[0_20px_60px_-45px_rgba(0,0,0,0.65)] ${
              isUser
                ? "border-[var(--accent)]/35 bg-[var(--accent)] text-white"
                : "border-[var(--border)] bg-[var(--card)] text-[var(--foreground)]"
            }`}
          >
            <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-[0.18em] opacity-80">
              {isUser ? <User size={14} /> : null}
              <span>{isUser ? "You" : "AgenticStack"}</span>
            </div>

            <div
              className={`prose prose-sm max-w-none leading-7 prose-li:my-1 prose-ul:my-3 prose-ol:my-3 prose-headings:mt-5 prose-headings:mb-2 ${
                isUser
                  ? "prose-invert prose-p:my-1 prose-headings:text-white prose-strong:text-white prose-code:text-white prose-a:text-white"
                  : "text-[var(--foreground)] prose-p:my-2 prose-p:text-[var(--foreground)] prose-headings:text-[var(--foreground)] prose-strong:text-[var(--foreground)] prose-code:text-[var(--accent)] prose-a:text-[var(--accent)] prose-li:text-[var(--foreground)] prose-ul:text-[var(--foreground)] prose-ol:text-[var(--foreground)]"
              }`}
            >
              {isUser && hitlResponse ? (
                <HitlResponseBubble action={hitlResponse.action} notes={hitlResponse.notes} />
              ) : isUser || !segments ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
              ) : (
                regularSegments.map((seg, i) =>
                  seg.type === "sql-results" ? (
                    <SqlResultsBlock key={i} sql={seg.sql} tableMarkdown={seg.tableMarkdown} />
                  ) : seg.type === "approval-creating" ? (
                    <div key={i} className="my-4 flex items-center gap-3 rounded-2xl border border-amber-500/25 bg-amber-500/10 px-5 py-4">
                      <Loader2 size={18} className="animate-spin text-amber-400" />
                      <div>
                        <p className="text-sm font-semibold text-amber-400">Creating approval...</p>
                        <p className="text-xs text-[var(--muted)]">Preparing the approval request for your review</p>
                      </div>
                    </div>
                  ) : seg.type === "markdown" ? (
                    <ReactMarkdown key={i} remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
                      {seg.content}
                    </ReactMarkdown>
                  ) : null,
                )
              )}
            </div>

            <button
              type="button"
              onClick={() => void handleCopy()}
              className={`absolute top-3 right-3 inline-flex h-7 w-7 items-center justify-center rounded-xl opacity-0 transition group-hover:opacity-100 ${
                isUser
                  ? "text-white/70 hover:bg-white/15 hover:text-white"
                  : "text-[var(--muted)] hover:bg-[color:color-mix(in_srgb,var(--foreground)_8%,transparent)] hover:text-[var(--foreground)]"
              }`}
              aria-label="Copy message"
            >
              {copied ? <Check size={13} /> : <Copy size={13} />}
            </button>
          </div>
        </div>
      )}

      {/* HITL approval cards — rendered outside the bubble, full-width, aligned with bot content */}
      {!isUser &&
        hitlSegments.map((seg, i) =>
          seg.type === "hitl-request" ? (
            <div key={`hitl-${i}`} className="w-full pl-12">
              <HitlApproval
                hitl={seg.payload}
                onAction={(actionId, controlValues, notes) =>
                  onHitlAction?.(seg.payload.id, actionId, controlValues, notes)
                }
                isResolved={resolvedHitlIds?.has(seg.payload.id)}
                resolvedAction={resolvedHitlIds?.has(seg.payload.id) ? "Resolved" : undefined}
              />
            </div>
          ) : null,
        )}

    </article>
  );
}

"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ShieldAlert,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  XCircle,
  MessageSquare,
  AlertTriangle,
  FileText,
  Wrench,
} from "lucide-react";
import type { HitlRequestPayload } from "@/lib/types";

const RISK_COLORS: Record<string, string> = {
  finance: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  legal: "bg-red-500/20 text-red-300 border-red-500/40",
  brand: "bg-purple-500/20 text-purple-300 border-purple-500/40",
  ops: "bg-blue-500/20 text-blue-300 border-blue-500/40",
  privacy: "bg-gray-500/20 text-gray-300 border-gray-500/40",
};

const EVIDENCE_BADGE: Record<string, string> = {
  RAG_POLICY: "bg-emerald-500/15 text-emerald-400",
  SQL_FACT: "bg-blue-500/15 text-blue-400",
  WEB_SOURCE: "bg-orange-500/15 text-orange-400",
};

type HitlApprovalProps = {
  hitl: HitlRequestPayload;
  onAction: (actionId: string, controlValues: Record<string, unknown>, notes?: string) => void;
  isResolved?: boolean;
  resolvedAction?: string;
};

export function HitlApproval({ hitl, onAction, isResolved, resolvedAction }: HitlApprovalProps) {
  const [controlValues, setControlValues] = useState<Record<string, unknown>>(() => {
    const defaults: Record<string, unknown> = {};
    for (const control of hitl.controls) {
      if (control.default !== undefined) defaults[control.id] = control.default;
      else if (control.type === "boolean") defaults[control.id] = false;
      else if (control.type === "number") defaults[control.id] = control.min ?? 0;
      else defaults[control.id] = "";
    }
    return defaults;
  });

  const [evidenceOpen, setEvidenceOpen] = useState(true);
  const [showNotes, setShowNotes] = useState(false);
  const [notes, setNotes] = useState("");

  // Validation warnings
  const warnings: string[] = [];
  if (hitl.evidence.length === 0) warnings.push("No supporting evidence provided");
  if (hitl.artifacts_preview.length === 0) warnings.push("No preview content available");
  const hasPoArtifact = hitl.artifacts_preview.some(
    (a) => a.type.includes("PURCHASE_ORDER") || a.type.includes("REPLENISHMENT")
  );
  if (hasPoArtifact) {
    const allContent = hitl.artifacts_preview.map((a) => a.content).join("");
    const hasNonZeroCost = /\$[1-9]/.test(allContent);
    if (!hasNonZeroCost) warnings.push("Purchase order appears to have a $0 total — review carefully");
  }

  function updateControl(id: string, value: unknown) {
    setControlValues((prev) => ({ ...prev, [id]: value }));
  }

  return (
    <div
      className={`my-3 overflow-hidden rounded-2xl border border-amber-500/35 shadow-xl shadow-amber-950/20 transition-opacity ${
        isResolved ? "opacity-60" : ""
      }`}
    >
      {/* ── Header ── */}
      <div className="border-b border-amber-500/25 bg-gradient-to-r from-amber-500/15 via-amber-500/8 to-transparent px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-500/15 ring-1 ring-amber-500/30">
              <ShieldAlert size={19} className="text-amber-400" />
            </div>
            <div>
              <div className="mb-0.5 flex items-center gap-2">
                <span className="text-[10px] font-bold uppercase tracking-widest text-amber-400">
                  Approval Required
                </span>
                {isResolved && (
                  <span className="rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-400">
                    ✓ {resolvedAction ?? "Resolved"}
                  </span>
                )}
              </div>
              <h3 className="text-sm font-semibold text-[var(--foreground)]">{hitl.title}</h3>
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {hitl.risk_tags.map((tag) => (
              <span
                key={tag}
                className={`rounded-full border px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                  RISK_COLORS[tag] ?? RISK_COLORS.ops
                }`}
              >
                {tag}
              </span>
            ))}
          </div>
        </div>

        {/* Summary */}
        <p className="mt-3 text-sm leading-6 text-[var(--foreground)]/80">{hitl.summary}</p>

        {/* Tools used */}
        {hitl.tools_used.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <Wrench size={10} className="text-amber-400/60" />
            {hitl.tools_used.map((t) => (
              <span
                key={t}
                className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-300"
              >
                {t}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── Validation warnings ── */}
      {warnings.length > 0 && (
        <div className="border-b border-amber-500/25 bg-amber-500/10 px-5 py-2.5">
          {warnings.map((w, i) => (
            <div key={i} className="flex items-center gap-2 text-xs text-amber-300">
              <AlertTriangle size={12} className="shrink-0" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Body ── */}
      <div className={isResolved ? "pointer-events-none" : ""}>
        {/* Two-column: left = evidence/preview · right = controls */}
        <div className="grid grid-cols-1 divide-y divide-[var(--border)] md:grid-cols-2 md:divide-x md:divide-y-0">
          {/* Left column */}
          <div className="space-y-4 bg-[color:color-mix(in_srgb,var(--foreground)_2%,transparent)] px-5 py-4">
            {/* Assumptions */}
            {hitl.assumptions.length > 0 && (
              <div>
                <p className="mb-2 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-[var(--muted)]">
                  <AlertTriangle size={10} />
                  Assumptions
                </p>
                <ul className="space-y-1 border-l-2 border-amber-500/25 pl-3">
                  {hitl.assumptions.map((a, i) => (
                    <li key={i} className="text-xs leading-5 text-[var(--foreground)]/80">
                      {a}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Evidence (collapsible) */}
            {hitl.evidence.length > 0 && (
              <div>
                <button
                  type="button"
                  onClick={() => setEvidenceOpen(!evidenceOpen)}
                  className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-[var(--muted)] transition hover:text-[var(--foreground)]"
                >
                  {evidenceOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                  Evidence ({hitl.evidence.length})
                </button>
                {evidenceOpen && (
                  <div className="mt-2 space-y-2">
                    {hitl.evidence.map((ev, i) => (
                      <div
                        key={i}
                        className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-2.5"
                      >
                        <div className="mb-1 flex items-center gap-2">
                          <span
                            className={`rounded-full px-2 py-0.5 text-[9px] font-semibold uppercase ${
                              EVIDENCE_BADGE[ev.type] ?? "bg-gray-500/15 text-gray-400"
                            }`}
                          >
                            {ev.type}
                          </span>
                          <span className="text-xs font-medium text-[var(--foreground)]">
                            {ev.label}
                          </span>
                        </div>
                        <p className="text-xs leading-5 text-[var(--muted)]">{ev.content}</p>
                        {ev.reference && (
                          <p className="mt-0.5 text-[10px] italic text-[var(--muted)]/60">
                            Ref: {ev.reference}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Artifact preview */}
            {hitl.artifacts_preview.length > 0 && (
              <div>
                <p className="mb-2 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-[var(--muted)]">
                  <FileText size={10} />
                  Preview
                </p>
                <div className="space-y-2">
                  {hitl.artifacts_preview.map((art, i) => (
                    <div
                      key={i}
                      className="overflow-hidden rounded-lg border border-[var(--border)]"
                    >
                      <div className="border-b border-[var(--border)] bg-[color:color-mix(in_srgb,var(--foreground)_4%,transparent)] px-3 py-1.5 text-[9px] font-bold uppercase tracking-widest text-[var(--muted)]">
                        {art.type}
                      </div>
                      <div className="bg-[var(--card)] p-3 text-xs leading-6 text-[var(--foreground)]">
                        {art.format === "markdown" || art.format === "table" ? (
                          <div className="prose prose-sm max-w-none prose-p:my-0 prose-headings:text-[var(--foreground)] prose-strong:text-[var(--foreground)]">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{art.content}</ReactMarkdown>
                          </div>
                        ) : (
                          <pre className="whitespace-pre-wrap font-mono text-[11px]">
                            {art.content}
                          </pre>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right column — controls */}
          <div className="px-5 py-4">
            {hitl.controls.length > 0 ? (
              <div>
                <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-[var(--muted)]">
                  Parameters
                </p>
                <div className="space-y-3">
                  {hitl.controls.map((ctrl) => (
                    <div key={ctrl.id}>
                      <label className="mb-1 block text-xs font-medium text-[var(--foreground)]">
                        {ctrl.label}
                        {ctrl.required && <span className="ml-0.5 text-red-400">*</span>}
                      </label>
                      {ctrl.help && (
                        <p className="mb-1 text-[10px] text-[var(--muted)]">{ctrl.help}</p>
                      )}

                      {ctrl.type === "select" && (
                        <select
                          value={String(controlValues[ctrl.id] ?? "")}
                          onChange={(e) => updateControl(ctrl.id, e.target.value)}
                          className="w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs text-[var(--foreground)] outline-none transition-colors focus:border-amber-400"
                        >
                          <option value="">Select...</option>
                          {ctrl.options?.map((opt) => (
                            <option key={opt} value={opt}>
                              {opt}
                            </option>
                          ))}
                        </select>
                      )}

                      {ctrl.type === "number" && (
                        <input
                          type="number"
                          value={Number(controlValues[ctrl.id] ?? 0)}
                          min={ctrl.min}
                          max={ctrl.max}
                          onChange={(e) => updateControl(ctrl.id, Number(e.target.value))}
                          className="w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs text-[var(--foreground)] outline-none transition-colors focus:border-amber-400"
                        />
                      )}

                      {ctrl.type === "boolean" && (
                        <label className="flex cursor-pointer items-center gap-2.5">
                          <button
                            type="button"
                            role="switch"
                            aria-checked={Boolean(controlValues[ctrl.id])}
                            onClick={() => updateControl(ctrl.id, !Boolean(controlValues[ctrl.id]))}
                            className={`relative h-5 w-9 rounded-full transition-colors ${
                              Boolean(controlValues[ctrl.id]) ? "bg-amber-500" : "bg-[var(--border)]"
                            }`}
                          >
                            <span
                              className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${
                                Boolean(controlValues[ctrl.id]) ? "left-4" : "left-0.5"
                              }`}
                            />
                          </button>
                          <span className="text-xs text-[var(--foreground)]">
                            {Boolean(controlValues[ctrl.id]) ? "Enabled" : "Disabled"}
                          </span>
                        </label>
                      )}

                      {ctrl.type === "text" && (
                        <textarea
                          value={String(controlValues[ctrl.id] ?? "")}
                          onChange={(e) => updateControl(ctrl.id, e.target.value)}
                          rows={2}
                          className="w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs text-[var(--foreground)] outline-none placeholder:text-[var(--muted)] transition-colors focus:border-amber-400"
                        />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex h-full items-center justify-center py-6 text-xs text-[var(--muted)]">
                No parameters to configure
              </div>
            )}
          </div>
        </div>

        {/* Notes textarea for request_changes */}
        {showNotes && (
          <div className="border-t border-[var(--border)] px-5 py-3">
            <label className="mb-1.5 block text-xs font-medium text-[var(--foreground)]">
              Changes requested
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="Describe what you'd like changed..."
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs text-[var(--foreground)] outline-none placeholder:text-[var(--muted)] transition-colors focus:border-amber-400"
            />
          </div>
        )}

        {/* ── On approve / On reject info ── */}
        {(hitl.on_approve?.next_step || hitl.on_reject?.fallback) && (
          <div className="border-t border-[var(--border)] px-5 py-2 space-y-1">
            {hitl.on_approve?.next_step && (
              <p className="text-[10px] text-[var(--muted)]">
                <span className="font-semibold">On approve:</span> {hitl.on_approve.next_step}
              </p>
            )}
            {hitl.on_reject?.fallback && (
              <p className="text-[10px] text-[var(--muted)]">
                <span className="font-semibold">On reject:</span> {hitl.on_reject.fallback}
              </p>
            )}
          </div>
        )}

        {/* ── Action bar ── */}
        {!isResolved && (
          <div className="flex flex-wrap items-center gap-2 border-t border-amber-500/20 bg-amber-500/5 px-5 py-3">
            <button
              type="button"
              onClick={() => onAction("approve", controlValues)}
              className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-emerald-500 active:scale-95"
            >
              <CheckCircle2 size={14} />
              Approve
            </button>
            <button
              type="button"
              onClick={() => {
                if (!showNotes) setShowNotes(true);
                else onAction("request_changes", controlValues, notes);
              }}
              className="inline-flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--card)] px-5 py-2 text-xs font-semibold text-[var(--foreground)] shadow-sm transition hover:bg-[color:color-mix(in_srgb,var(--foreground)_8%,transparent)] active:scale-95"
            >
              <MessageSquare size={14} />
              {showNotes ? "Send Changes" : "Request Changes"}
            </button>
            <button
              type="button"
              onClick={() => onAction("reject", controlValues)}
              className="inline-flex items-center gap-2 rounded-xl border border-red-500/30 px-5 py-2 text-xs font-semibold text-red-400 transition hover:bg-red-500/10 active:scale-95"
            >
              <XCircle size={14} />
              Reject
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

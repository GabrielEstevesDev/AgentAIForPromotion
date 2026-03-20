"use client";

import React, { useState } from "react";
import {
  Activity,
  Brain,
  ChevronDown,
  ChevronRight,
  Clock,
  Database,
  GitBranch,
  Globe,
  Hammer,
  Pause,
  Play,
  Search,
  Sparkles,
  Wrench,
  Zap,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type TraceEvent = {
  type: string;
  ts: number;
  name?: string;
  duration?: number;
  call_number?: number;
  input?: string;
  output_preview?: string;
  length?: number;
  action?: string;
  message?: string;
  total_duration?: number;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(seconds: number): string {
  if (seconds < 0.001) return "<1ms";
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  return `${seconds.toFixed(2)}s`;
}

function getEventIcon(event: TraceEvent) {
  switch (event.type) {
    case "user_message":
      return <Sparkles size={12} />;
    case "node_start":
    case "node_end":
      return getNodeIcon(event.name ?? "");
    case "llm_start":
    case "llm_end":
      return <Brain size={12} />;
    case "tool_start":
    case "tool_end":
      return getToolIcon(event.name ?? "");
    case "hitl_interrupt":
    case "hitl_resume":
      return <Pause size={12} />;
    case "graph_end":
      return <Zap size={12} />;
    case "error":
      return <Activity size={12} />;
    default:
      return <GitBranch size={12} />;
  }
}

function getNodeIcon(name: string) {
  switch (name) {
    case "classify":
      return <Search size={12} />;
    case "plan_and_call":
    case "force_respond":
    case "post_approve":
      return <Brain size={12} />;
    case "execute_tools":
      return <Wrench size={12} />;
    case "fast_response":
    case "direct_query":
    case "direct_chart":
      return <Zap size={12} />;
    case "extract_hitl":
    case "hitl_gate":
      return <Pause size={12} />;
    case "summarize_if_needed":
      return <GitBranch size={12} />;
    default:
      return <GitBranch size={12} />;
  }
}

function getToolIcon(name: string) {
  switch (name) {
    case "sql_query":
    case "query_library":
      return <Database size={12} />;
    case "web_search":
      return <Globe size={12} />;
    case "python_executor":
      return <Hammer size={12} />;
    default:
      return <Wrench size={12} />;
  }
}

function getEventColor(event: TraceEvent): string {
  switch (event.type) {
    case "node_start":
      return "text-blue-400";
    case "node_end":
      return "text-blue-300";
    case "llm_start":
      return "text-purple-400";
    case "llm_end":
      return "text-purple-300";
    case "tool_start":
      return "text-emerald-400";
    case "tool_end":
      return "text-emerald-300";
    case "hitl_interrupt":
    case "hitl_resume":
      return "text-amber-400";
    case "error":
      return "text-red-400";
    case "graph_end":
      return "text-cyan-400";
    default:
      return "text-[var(--muted)]";
  }
}

function getEventLabel(event: TraceEvent): string {
  switch (event.type) {
    case "user_message":
      return `Message received (${event.length ?? 0} chars)`;
    case "node_start":
      return `${event.name}`;
    case "node_end":
      return `${event.name} completed`;
    case "llm_start":
      return `LLM call #${event.call_number}`;
    case "llm_end":
      return `LLM call #${event.call_number} completed`;
    case "tool_start":
      return `${event.name}`;
    case "tool_end":
      return `${event.name} completed`;
    case "hitl_interrupt":
      return "Graph paused (HITL)";
    case "hitl_resume":
      return `Graph resumed (${event.action})`;
    case "graph_end":
      return "Graph completed";
    case "error":
      return `Error: ${event.message ?? "unknown"}`;
    default:
      return event.type;
  }
}

// ---------------------------------------------------------------------------
// Derived summary from trace events
// ---------------------------------------------------------------------------

type TraceSummary = {
  totalDuration: number;
  nodeSequence: string[];
  toolCalls: { name: string; duration: number; input?: string }[];
  llmCalls: { number: number; duration: number }[];
  mode?: string;
};

function buildSummary(events: TraceEvent[]): TraceSummary {
  const nodeSequence: string[] = [];
  const toolCalls: { name: string; duration: number; input?: string }[] = [];
  const llmCalls: { number: number; duration: number }[] = [];
  let totalDuration = 0;

  for (const ev of events) {
    if (ev.type === "node_start" && ev.name) {
      nodeSequence.push(ev.name);
    }
    if (ev.type === "tool_end" && ev.name) {
      toolCalls.push({ name: ev.name, duration: ev.duration ?? 0, input: ev.input });
    }
    if (ev.type === "llm_end") {
      llmCalls.push({ number: ev.call_number ?? 0, duration: ev.duration ?? 0 });
    }
    if (ev.type === "graph_end") {
      totalDuration = ev.total_duration ?? 0;
    }
  }

  return { totalDuration, nodeSequence, toolCalls, llmCalls };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function TracePanel({ events }: { events: TraceEvent[] }) {
  const [expanded, setExpanded] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);
  const summary = buildSummary(events);

  if (!events.length) return null;

  return (
    <div className="mt-2 w-full overflow-hidden rounded-xl border border-[var(--border)] bg-[color:color-mix(in_srgb,var(--foreground)_2%,transparent)]">
      {/* Header */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-left transition-colors hover:bg-[color:color-mix(in_srgb,var(--foreground)_5%,transparent)]"
      >
        <Activity size={14} className="text-[var(--accent)]" />
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
          Trace Inspector
        </span>
        <span className="ml-auto flex items-center gap-3 text-xs text-[var(--muted)]">
          {summary.nodeSequence.length > 0 && (
            <span>{summary.nodeSequence.length} nodes</span>
          )}
          {summary.toolCalls.length > 0 && (
            <span>{summary.toolCalls.length} tool calls</span>
          )}
          {summary.llmCalls.length > 0 && (
            <span>{summary.llmCalls.length} LLM calls</span>
          )}
          {summary.totalDuration > 0 && (
            <span className="flex items-center gap-1">
              <Clock size={11} />
              {formatDuration(summary.totalDuration)}
            </span>
          )}
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-[var(--border)]">
          {/* Summary cards */}
          <div className="grid grid-cols-3 gap-px bg-[var(--border)]">
            {/* Node flow */}
            <div className="bg-[var(--card)] px-4 py-3">
              <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-[var(--muted)]">
                Node Flow
              </div>
              <div className="flex flex-wrap gap-1">
                {summary.nodeSequence.map((node, i) => (
                  <React.Fragment key={i}>
                    {i > 0 && (
                      <span className="self-center text-[10px] text-[var(--muted)]">&rarr;</span>
                    )}
                    <span className="rounded-md bg-blue-500/10 px-1.5 py-0.5 text-[10px] font-medium text-blue-400">
                      {node}
                    </span>
                  </React.Fragment>
                ))}
              </div>
            </div>

            {/* Tool calls */}
            <div className="bg-[var(--card)] px-4 py-3">
              <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-[var(--muted)]">
                Tools Used
              </div>
              {summary.toolCalls.length === 0 ? (
                <span className="text-xs text-[var(--muted)]">None</span>
              ) : (
                <div className="flex flex-col gap-1">
                  {summary.toolCalls.map((tool, i) => (
                    <div key={i} className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-400">
                        {getToolIcon(tool.name)}
                        {tool.name}
                      </span>
                      <span className="text-[10px] text-[var(--muted)]">
                        {formatDuration(tool.duration)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* LLM calls */}
            <div className="bg-[var(--card)] px-4 py-3">
              <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-[var(--muted)]">
                LLM Calls
              </div>
              {summary.llmCalls.length === 0 ? (
                <span className="text-xs text-[var(--muted)]">None (fast lane)</span>
              ) : (
                <div className="flex flex-col gap-1">
                  {summary.llmCalls.map((llm, i) => (
                    <div key={i} className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1 text-[10px] font-medium text-purple-400">
                        <Brain size={10} />
                        Call #{llm.number}
                      </span>
                      <span className="text-[10px] text-[var(--muted)]">
                        {formatDuration(llm.duration)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Timeline toggle */}
          <div className="border-t border-[var(--border)]">
            <button
              type="button"
              onClick={() => setShowTimeline(!showTimeline)}
              className="flex w-full items-center gap-2 px-4 py-2 text-left transition-colors hover:bg-[color:color-mix(in_srgb,var(--foreground)_5%,transparent)]"
            >
              <Play size={11} className="text-[var(--muted)]" />
              <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted)]">
                Full Timeline ({events.length} events)
              </span>
              {showTimeline ? (
                <ChevronDown size={12} className="ml-auto text-[var(--muted)]" />
              ) : (
                <ChevronRight size={12} className="ml-auto text-[var(--muted)]" />
              )}
            </button>
          </div>

          {/* Full timeline */}
          {showTimeline && (
            <div className="max-h-80 overflow-y-auto border-t border-[var(--border)] px-4 py-2">
              {events.map((event, i) => (
                <div
                  key={i}
                  className="flex items-start gap-3 border-l border-[var(--border)] py-1.5 pl-3"
                >
                  {/* Timeline dot */}
                  <div className={`mt-0.5 flex-shrink-0 ${getEventColor(event)}`}>
                    {getEventIcon(event)}
                  </div>

                  {/* Content */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className={`text-[11px] font-medium ${getEventColor(event)}`}>
                        {getEventLabel(event)}
                      </span>
                      {event.duration != null && (
                        <span className="rounded bg-[color:color-mix(in_srgb,var(--foreground)_8%,transparent)] px-1.5 py-0.5 text-[9px] font-mono text-[var(--muted)]">
                          {formatDuration(event.duration)}
                        </span>
                      )}
                      <span className="ml-auto text-[9px] font-mono text-[var(--muted)]">
                        +{formatDuration(event.ts)}
                      </span>
                    </div>

                    {/* Tool input preview */}
                    {event.type === "tool_start" && event.input && (
                      <div className="mt-0.5 truncate text-[10px] font-mono text-[var(--muted)]">
                        {event.input}
                      </div>
                    )}

                    {/* Tool output preview */}
                    {event.type === "tool_end" && event.output_preview && (
                      <div className="mt-0.5 truncate text-[10px] font-mono text-[var(--muted)]">
                        {event.output_preview}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

"use client";

import { useEffect, useRef } from "react";
import {
  ArrowUpRight,
  Bot,
  Database,
  BookOpen,
  Globe,
  BarChart3,
  Shield,
  LayoutGrid,
  AlertTriangle,
  Clock,
} from "lucide-react";

import { MessageBubble } from "@/app/components/MessageBubble";
import type { ChatMessage } from "@/lib/api";
import type { UseCaseCardsPayload } from "@/lib/types";

type RateLimitError = {
  type: "global_limit" | "user_limit";
  message: string;
};

type ChatAreaProps = {
  title: string;
  messages?: ChatMessage[];
  onPromptSelect?: (prompt: string) => void;
  isLoading?: boolean;
  onHitlAction?: (hitlId: string, actionId: string, controlValues: Record<string, unknown>, notes?: string) => void;
  onUseCaseCards?: (payload: UseCaseCardsPayload) => void;
  onOpenDrawer?: () => void;
  resolvedHitlIds?: Set<string>;
  rateLimitError?: RateLimitError | null;
};

const CATEGORY_ICONS: Record<string, typeof Database> = {
  SQL: Database,
  RAG: BookOpen,
  WEB: Globe,
  PYTHON_CHART: BarChart3,
  HITL: Shield,
};

const BADGE_COLORS: Record<string, string> = {
  SQL: "bg-blue-500/15 text-blue-400 border-blue-500/25",
  RAG: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
  WEB: "bg-orange-500/15 text-orange-400 border-orange-500/25",
  PYTHON_CHART: "bg-purple-500/15 text-purple-400 border-purple-500/25",
  HITL: "bg-amber-500/15 text-amber-400 border-amber-500/25",
};

const BADGE_LABELS: Record<string, string> = {
  HITL: "Approval",
};

const frontActions = [
  {
    id: "front-sql",
    category: "SQL",
    title: "Top Products by Revenue",
    description: "See which products generate the most revenue",
    tool_badges: ["SQL"],
    prompt: "Show me the top 10 products by revenue.",
    requires_hitl: false,
  },
  {
    id: "front-rag",
    category: "RAG",
    title: "Return Policy",
    description: "Look up return and refund policies",
    tool_badges: ["RAG"],
    prompt: "What is the return policy?",
    requires_hitl: false,
  },
  {
    id: "front-web",
    category: "WEB",
    title: "E-commerce Trends",
    description: "Latest industry trends and insights",
    tool_badges: ["WEB"],
    prompt: "What are the latest e-commerce trends for 2025?",
    requires_hitl: false,
  },
  {
    id: "front-chart",
    category: "PYTHON_CHART",
    title: "Revenue by Month Chart",
    description: "Visualize monthly revenue trends",
    tool_badges: ["SQL", "PYTHON_CHART"],
    prompt: "Create a bar chart of revenue by month.",
    requires_hitl: false,
  },
  {
    id: "front-hitl",
    category: "HITL",
    title: "Draft Refund Email",
    description: "Generate a customer refund email for review",
    tool_badges: ["RAG", "SQL", "HITL"],
    prompt: "Draft a refund email for the most recent cancelled order.",
    requires_hitl: true,
  },
  {
    id: "front-prospect",
    category: "SQL",
    title: "AI Use Cases for Clients",
    description: "Discover top AI workflows to demo to prospects",
    tool_badges: ["SQL", "RAG"],
    prompt: "What are the top 5 AI use cases we could demo to a potential e-commerce client? Run a live example of the most impactful one.",
    requires_hitl: false,
  },
];

export function ChatArea({
  title,
  messages = [],
  onPromptSelect,
  isLoading = false,
  onHitlAction,
  onUseCaseCards,
  onOpenDrawer,
  resolvedHitlIds,
  rateLimitError,
}: ChatAreaProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const prevMessagesLengthRef = useRef(messages.length);

  useEffect(() => {
    const lastMessage = messages[messages.length - 1];
    if (messages.length > prevMessagesLengthRef.current && lastMessage?.role === "user") {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
    prevMessagesLengthRef.current = messages.length;
  }, [messages]);

  const lastMessageIsUser =
    messages.length > 0 && messages[messages.length - 1]?.role === "user";
  const showTypingIndicator = isLoading && (messages.length === 0 || lastMessageIsUser);

  const isStreamingLastMessage =
    isLoading && messages.length > 0 && messages[messages.length - 1]?.role === "assistant";

  return (
    <section className="relative flex flex-1 flex-col px-4 pb-36 pt-20 sm:px-8 md:pt-10">
      <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6">
        <div className="border-b border-[var(--border)] pb-3">
          <h2 className="text-base font-semibold tracking-tight truncate">{title}</h2>
        </div>

        {rateLimitError && messages.length === 0 && (
          <RateLimitBanner
            type={rateLimitError.type}
            message={rateLimitError.message}
          />
        )}

        {messages.length === 0 && !isLoading ? (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {frontActions.map((action) => {
                const CategoryIcon = CATEGORY_ICONS[action.category] ?? Database;
                return (
                  <button
                    type="button"
                    key={action.id}
                    onClick={() => onPromptSelect?.(action.prompt)}
                    className="rounded-[1.6rem] border border-[var(--border)] bg-[var(--card)] p-5 backdrop-blur transition hover:-translate-y-0.5 hover:border-[var(--accent)]/35 text-left"
                  >
                    <div className="mb-3 flex items-center justify-between text-[var(--muted)]">
                      <CategoryIcon size={16} className="text-[var(--accent)]" />
                      <div className="flex items-center gap-1.5">
                        {action.tool_badges.map((badge) => (
                          <span
                            key={badge}
                            className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${BADGE_COLORS[badge] ?? "bg-gray-500/15 text-gray-400 border-gray-500/25"}`}
                          >
                            {BADGE_LABELS[badge] ?? badge}
                          </span>
                        ))}
                        {action.requires_hitl && (
                          <Shield size={12} className="text-amber-400" />
                        )}
                        <ArrowUpRight size={14} />
                      </div>
                    </div>
                    <p className="text-sm font-medium text-[var(--foreground)]">{action.title}</p>
                    <p className="mt-1 text-xs text-[var(--muted)]">{action.description}</p>
                  </button>
                );
              })}
            </div>

            {/* Use Cases button */}
            {onOpenDrawer && (
              <div className="flex justify-center">
                <button
                  type="button"
                  onClick={onOpenDrawer}
                  className="inline-flex items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--card)] px-5 py-2.5 text-sm font-medium text-[var(--muted)] transition hover:border-[var(--accent)]/35 hover:text-[var(--foreground)]"
                >
                  <LayoutGrid size={16} />
                  Browse All Use Cases
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-5">
            {messages.map((message, index) => (
              <MessageBubble
                key={`${message.role}-${message.content.slice(0, 24)}-${index}`}
                message={message}
                onHitlAction={onHitlAction}
                onUseCaseCards={onUseCaseCards}
                isStreaming={isStreamingLastMessage && index === messages.length - 1}
                resolvedHitlIds={resolvedHitlIds}
              />
            ))}

            {showTypingIndicator && (
              <article className="flex gap-3 justify-start">
                <div className="mt-1 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent)]/15 text-[var(--accent)]">
                  <Bot size={18} />
                </div>
                <div className="rounded-[1.6rem] border border-[var(--border)] bg-[var(--card)] px-5 py-4 shadow-[0_20px_60px_-45px_rgba(0,0,0,0.65)]">
                  <div className="mb-3 text-xs uppercase tracking-[0.18em] opacity-80">AgenticStack</div>
                  <div className="flex gap-1.5 items-center">
                    <span
                      className="h-2 w-2 rounded-full bg-[var(--muted)] animate-bounce"
                      style={{ animationDelay: "0ms" }}
                    />
                    <span
                      className="h-2 w-2 rounded-full bg-[var(--muted)] animate-bounce"
                      style={{ animationDelay: "160ms" }}
                    />
                    <span
                      className="h-2 w-2 rounded-full bg-[var(--muted)] animate-bounce"
                      style={{ animationDelay: "320ms" }}
                    />
                  </div>
                </div>
              </article>
            )}

            {rateLimitError && (
              <RateLimitBanner
                type={rateLimitError.type}
                message={rateLimitError.message}
              />
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>
    </section>
  );
}

function RateLimitBanner({
  type,
  message,
}: {
  type: "global_limit" | "user_limit";
  message: string;
}) {
  const isGlobal = type === "global_limit";
  const Icon = isGlobal ? Clock : AlertTriangle;

  const colors = isGlobal
    ? {
        border: "border-blue-500/25",
        bg: "bg-gradient-to-br from-blue-500/10 to-blue-600/5",
        iconBg: "bg-blue-500/15",
        icon: "text-blue-400",
        title: "text-blue-300",
        badge: "bg-blue-500/20 text-blue-300 border-blue-500/30",
      }
    : {
        border: "border-amber-500/25",
        bg: "bg-gradient-to-br from-amber-500/10 to-amber-600/5",
        iconBg: "bg-amber-500/15",
        icon: "text-amber-400",
        title: "text-amber-300",
        badge: "bg-amber-500/20 text-amber-300 border-amber-500/30",
      };

  const titleText = isGlobal ? "Daily Capacity Reached" : "Daily Limit Reached";
  const badgeText = isGlobal ? "Platform Limit" : "Per-User Limit";

  return (
    <div className={`mx-auto w-full max-w-2xl rounded-[1.6rem] border ${colors.border} ${colors.bg} p-6 backdrop-blur shadow-[0_20px_60px_-45px_rgba(0,0,0,0.65)]`}>
      <div className="flex items-start gap-4">
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${colors.iconBg}`}>
          <Icon size={20} className={colors.icon} />
        </div>
        <div className="flex-1 space-y-2">
          <div className="flex items-center gap-2.5">
            <p className={`text-sm font-semibold ${colors.title}`}>{titleText}</p>
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${colors.badge}`}>
              {badgeText}
            </span>
          </div>
          <p className="text-sm leading-relaxed text-[var(--muted)]">{message}</p>
          <p className="text-xs text-[var(--muted)]/60">Limits reset daily at midnight UTC.</p>
        </div>
      </div>
    </div>
  );
}

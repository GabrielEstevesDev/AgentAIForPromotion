"use client";

import { useCallback, useEffect, useRef, useState, useTransition } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Check,
  Database,
  FileText,
  Menu,
  MessageSquare,
  MessageSquarePlus,
  PanelLeftClose,
  Pencil,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

import { getConversations, type ConversationSummary } from "@/lib/api";
import { ThemeToggle } from "@/app/components/ThemeToggle";

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const renameInputRef = useRef<HTMLInputElement | null>(null);

  const loadConversations = useCallback(async () => {
    setIsLoading(true);
    setHasError(false);
    try {
      const items = await getConversations();
      setConversations(items);
    } catch {
      setConversations([]);
      setHasError(true);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadConversations();
  }, [pathname, loadConversations]);

  useEffect(() => {
    function handleUpdate() {
      void loadConversations();
    }
    window.addEventListener("aria:conversation-updated", handleUpdate);
    return () => window.removeEventListener("aria:conversation-updated", handleUpdate);
  }, [loadConversations]);

  useEffect(() => {
    setIsOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (renamingId) {
      renameInputRef.current?.focus();
      renameInputRef.current?.select();
    }
  }, [renamingId]);

  function startRename(conversationId: string, currentTitle: string) {
    setRenamingId(conversationId);
    setRenameValue(currentTitle);
  }

  async function commitRename(conversationId: string) {
    const title = renameValue.trim();
    setRenamingId(null);

    if (!title) return;
    const existing = conversations.find((c) => c.id === conversationId)?.title;
    if (title === existing) return;

    try {
      const response = await fetch(`/api/conversations/${conversationId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      if (response.ok) {
        setConversations((current) =>
          current.map((c) => (c.id === conversationId ? { ...c, title } : c)),
        );
      }
    } catch {
      // Silent fail — list stays unchanged
    }
  }

  async function handleDeleteConversation(conversationId: string) {
    if (deletingId === conversationId) {
      return;
    }

    setDeletingId(conversationId);

    try {
      const response = await fetch(`/api/conversations/${conversationId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("Failed to delete conversation.");
      }

      setConversations((current) =>
        current.filter((conversation) => conversation.id !== conversationId),
      );

      if (pathname === `/chat/${conversationId}`) {
        startTransition(() => {
          router.push("/chat");
          router.refresh();
        });
      }
    } catch {
      setHasError(true);
    } finally {
      setDeletingId((current) => (current === conversationId ? null : current));
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="fixed left-4 top-4 z-30 inline-flex h-11 w-11 items-center justify-center rounded-full border border-[var(--sidebar-border)] bg-[var(--card)] text-[var(--foreground)] shadow-lg backdrop-blur transition hover:border-[var(--accent)] md:hidden"
        aria-label="Open sidebar"
      >
        <Menu size={18} />
      </button>

      <div
        className={`fixed inset-0 z-20 bg-black/30 backdrop-blur-sm transition md:hidden ${
          isOpen ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={() => setIsOpen(false)}
      />

      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-80 flex-col border-r border-[var(--sidebar-border)] bg-[var(--sidebar)] px-4 py-5 backdrop-blur transition-transform duration-300 md:sticky md:top-0 md:h-screen md:w-72 md:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="mb-6 flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--muted)]">Aria</p>
            <h1 className="mt-1 text-xl font-semibold">Assistant Console</h1>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-[var(--sidebar-border)] bg-[var(--card)] text-[var(--foreground)] transition hover:border-[var(--accent)] md:hidden"
              aria-label="Close sidebar"
            >
              <PanelLeftClose size={18} />
            </button>
          </div>
        </div>

        <Link
          href="/chat"
          className="mb-4 inline-flex items-center justify-center gap-2 rounded-2xl bg-[var(--accent)] px-4 py-3 text-sm font-medium text-white transition hover:bg-[var(--accent-strong)]"
        >
          <MessageSquarePlus size={16} />
          New conversation
        </Link>

        {/* Navigation tabs */}
        <nav className="mb-4 flex gap-1 rounded-2xl border border-[var(--sidebar-border)] bg-[var(--card)] p-1.5">
          {[
            { href: "/chat", label: "Chat", icon: MessageSquare },
            { href: "/database", label: "Database", icon: Database },
            { href: "/documents", label: "Documents", icon: FileText },
          ].map(({ href, label, icon: Icon }) => {
            const isActive =
              href === "/chat"
                ? pathname.startsWith("/chat")
                : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`flex flex-1 items-center justify-center gap-1.5 rounded-xl px-2 py-2 text-xs font-medium transition ${
                  isActive
                    ? "bg-[color:color-mix(in_srgb,var(--accent)_15%,transparent)] text-[var(--accent)]"
                    : "text-[var(--muted)] hover:bg-[color:color-mix(in_srgb,var(--foreground)_5%,transparent)] hover:text-[var(--foreground)]"
                }`}
              >
                <Icon size={14} />
                {label}
              </Link>
            );
          })}
        </nav>

        {pathname.startsWith("/chat") && (
        <div className="flex flex-1 flex-col rounded-3xl border border-[var(--sidebar-border)] bg-[var(--card)] p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium">
            <Sparkles size={16} className="text-[var(--accent)]" />
            Recent conversations
          </div>

          <div className="flex-1 space-y-2 overflow-y-auto pr-1">
            {isLoading ? (
              Array.from({ length: 4 }, (_, index) => (
                <div
                  key={index}
                  className="h-14 animate-pulse rounded-2xl bg-[color:color-mix(in_srgb,var(--foreground)_8%,transparent)]"
                />
              ))
            ) : (
              conversations.map((conversation) => {
                const href = `/chat/${conversation.id}`;
                const isActive = pathname === href;
                const isDeleting = deletingId === conversation.id;
                const isRenaming = renamingId === conversation.id;

                return (
                  <div
                    key={conversation.id}
                    className={`group relative flex items-center rounded-2xl border px-3 py-3 text-sm transition ${
                      isActive
                        ? "border-[var(--accent)] bg-[var(--card-strong)] text-[var(--foreground)]"
                        : "border-transparent text-[var(--muted)] hover:border-[var(--sidebar-border)] hover:bg-[var(--card-strong)] hover:text-[var(--foreground)]"
                    }`}
                  >
                    {isRenaming ? (
                      <div className="flex min-w-0 flex-1 items-center gap-1">
                        <input
                          ref={renameInputRef}
                          type="text"
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") void commitRename(conversation.id);
                            if (e.key === "Escape") setRenamingId(null);
                          }}
                          onBlur={() => void commitRename(conversation.id)}
                          className="min-w-0 flex-1 rounded-lg bg-[color:color-mix(in_srgb,var(--foreground)_8%,transparent)] px-2 py-0.5 text-sm text-[var(--foreground)] outline-none ring-1 ring-[var(--accent)]/50"
                        />
                        <button
                          type="button"
                          onClick={() => void commitRename(conversation.id)}
                          className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-[var(--accent)] hover:bg-[color:color-mix(in_srgb,var(--accent)_12%,transparent)]"
                          aria-label="Save rename"
                        >
                          <Check size={12} />
                        </button>
                        <button
                          type="button"
                          onClick={() => setRenamingId(null)}
                          className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-[var(--muted)] hover:bg-[color:color-mix(in_srgb,var(--foreground)_8%,transparent)]"
                          aria-label="Cancel rename"
                        >
                          <X size={12} />
                        </button>
                      </div>
                    ) : (
                      <>
                        <Link href={href} className="min-w-0 flex-1 pr-2">
                          <div className="truncate font-medium">{conversation.title}</div>
                          <div className="mt-1 text-xs text-[var(--muted)]">
                            {formatRelativeDate(conversation.updatedAt)}
                          </div>
                        </Link>
                        <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-0.5 opacity-0 transition group-hover:opacity-100">
                          <button
                            type="button"
                            onClick={() => startRename(conversation.id, conversation.title)}
                            className="inline-flex h-7 w-7 items-center justify-center rounded-full text-[var(--muted)] hover:bg-[color:color-mix(in_srgb,var(--foreground)_8%,transparent)] hover:text-[var(--foreground)]"
                            aria-label={`Rename ${conversation.title}`}
                          >
                            <Pencil size={13} />
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleDeleteConversation(conversation.id)}
                            disabled={isDeleting || isPending}
                            className="inline-flex h-7 w-7 items-center justify-center rounded-full text-[var(--muted)] hover:bg-[color:color-mix(in_srgb,var(--foreground)_8%,transparent)] hover:text-[var(--foreground)] disabled:cursor-not-allowed disabled:opacity-100 disabled:hover:bg-transparent"
                            aria-label={`Delete ${conversation.title}`}
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                );
              })
            )}

            {!isLoading && conversations.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-[var(--sidebar-border)] px-4 py-6 text-sm text-[var(--muted)]">
                {hasError
                  ? "Unable to load conversations right now."
                  : "No saved conversations yet."}
              </div>
            ) : null}
          </div>
        </div>
        )}
      </aside>
    </>
  );
}

function formatRelativeDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Recent";
  }

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
  }).format(date);
}

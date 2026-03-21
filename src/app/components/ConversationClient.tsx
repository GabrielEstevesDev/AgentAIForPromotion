"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useChat } from "ai/react";

import { ChatArea } from "@/app/components/ChatArea";
import { ChatInput } from "@/app/components/ChatInput";
import { UseCasesDrawer } from "@/app/components/UseCasesDrawer";
import type { ChatMessage, TraceEvent } from "@/lib/api";
import { getSessionId } from "@/lib/session";
import type { UseCaseCardsPayload } from "@/lib/types";

type ConversationClientProps = {
  initialConversationId?: string;
  initialMessages?: ChatMessage[];
  title: string;
};

export function ConversationClient({
  initialConversationId,
  initialMessages = [],
  title,
}: ConversationClientProps) {
  const router = useRouter();
  const [activeConversationId, setActiveConversationId] = useState(initialConversationId);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [rateLimitError, setRateLimitError] = useState<{
    type: "global_limit" | "user_limit";
    message: string;
  } | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [useCaseData, setUseCaseData] = useState<UseCaseCardsPayload | null>(null);
  const [resolvedHitlIds, setResolvedHitlIds] = useState<Set<string>>(() => {
    // Scan initial messages for already-resolved HITL requests
    const resolved = new Set<string>();
    for (let i = 0; i < initialMessages.length; i++) {
      const msg = initialMessages[i];
      if (msg.role === "user" && msg.content.startsWith("[HITL Response]")) {
        // Find the preceding HITL_REQUEST to extract its id
        const hitlIdMatch = msg.content.match(/hitlId:([^\s,]+)/);
        if (hitlIdMatch) resolved.add(hitlIdMatch[1]);
      }
    }
    return resolved;
  });

  // Track whether onError fired during an append call (ref survives async gaps)
  const hadStreamErrorRef = useRef(false);

  // Trace map: messageId → trace events (populated from initial data + live annotations)
  const traceMapRef = useRef<Map<string, TraceEvent[]>>(new Map());
  // Populate from initial messages on first render
  if (traceMapRef.current.size === 0 && initialMessages.length > 0) {
    for (const msg of initialMessages) {
      if (msg.id && msg.trace && msg.trace.length > 0) {
        traceMapRef.current.set(msg.id, msg.trace);
      }
    }
  }
  // Force re-render when trace map updates from live annotations
  const [traceVersion, setTraceVersion] = useState(0);

  useEffect(() => {
    setActiveConversationId(initialConversationId);
    if (initialConversationId) {
      sessionStorage.setItem("ephemeral_conversation_id", initialConversationId);
    }
  }, [initialConversationId]);

  // Read admin token from localStorage for rate-limit bypass
  const adminToken = typeof window !== "undefined" ? localStorage.getItem("adminToken") : null;

  const { messages, input, setInput, append, status, error } = useChat({
    api: "/api/chat",
    id: initialConversationId,
    headers: adminToken ? { "x-admin-token": adminToken } : undefined,
    initialMessages: initialMessages.map((message, index) => ({
      id: message.id ?? `${message.role}-${index}`,
      role: message.role,
      content: message.content,
    })),
    body: activeConversationId ? { conversationId: activeConversationId } : undefined,
    onError: (err) => {
      // Flag that an error occurred (checked after await append to skip navigation)
      hadStreamErrorRef.current = true;
      // Intercept rate-limit errors to show styled banner instead of raw JSON
      try {
        const parsed = JSON.parse(err.message);
        if (parsed.error === "global_limit" || parsed.error === "user_limit") {
          setRateLimitError({ type: parsed.error, message: parsed.message });
          return;
        }
      } catch {
        // Not a rate-limit error — let default handling proceed
      }
    },
    onFinish: (message) => {
      // Extract trace from annotations on the finished message
      const annotations = (message as unknown as Record<string, unknown>).annotations;
      if (Array.isArray(annotations)) {
        for (const ann of annotations) {
          if (
            ann &&
            typeof ann === "object" &&
            (ann as Record<string, unknown>).type === "trace"
          ) {
            const events = (ann as Record<string, unknown>).events;
            if (Array.isArray(events) && message.id) {
              traceMapRef.current.set(message.id, events as TraceEvent[]);
              setTraceVersion((v) => v + 1);
            }
          }
        }
      }

      // Fallback: fetch traces from backend if not found in annotations
      const convId = activeConversationId;
      if (convId && !traceMapRef.current.has(message.id)) {
        fetch(`/api/conversations/${convId}/traces`)
          .then((res) => res.ok ? res.json() : [])
          .then((traces: { messageId: string; trace: TraceEvent[] }[]) => {
            let updated = false;
            for (const t of traces) {
              if (!traceMapRef.current.has(t.messageId) && t.trace?.length) {
                traceMapRef.current.set(t.messageId, t.trace);
                updated = true;
              }
            }
            if (updated) setTraceVersion((v) => v + 1);
          })
          .catch(() => {});
      }

      // Immediate refresh to add new conversation to sidebar
      window.dispatchEvent(new CustomEvent("aria:conversation-updated"));
      // Delayed refresh to pick up the auto-generated title from backend
      setTimeout(() => {
        window.dispatchEvent(new CustomEvent("aria:conversation-updated"));
      }, 3000);
    },
  });

  const uiMessages = useMemo<ChatMessage[]>(
    () =>
      messages
        .filter(
          (message) =>
            message.role === "user" ||
            message.role === "assistant" ||
            message.role === "system",
        )
        .map((message) => {
          // Check trace map first (from initial data or onFinish)
          let trace = message.id ? traceMapRef.current.get(message.id) : undefined;

          // Also check live annotations on the message object
          if (!trace && message.annotations) {
            for (const ann of message.annotations) {
              if (
                ann &&
                typeof ann === "object" &&
                !Array.isArray(ann) &&
                (ann as Record<string, unknown>).type === "trace"
              ) {
                const events = (ann as Record<string, unknown>).events;
                if (Array.isArray(events)) {
                  trace = events as TraceEvent[];
                  // Also cache it
                  if (message.id) {
                    traceMapRef.current.set(message.id, trace);
                  }
                }
              }
            }
          }

          return {
            id: message.id,
            role: message.role as ChatMessage["role"],
            content: message.content,
            trace,
          };
        }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [messages, traceVersion],
  );

  const renderedMessages = useMemo(() => {
    // Don't show raw error bubble when it's a rate-limit error (handled by banner)
    if (rateLimitError) {
      return uiMessages;
    }

    const message = submitError ?? error?.message;
    if (!message) {
      return uiMessages;
    }

    // Also suppress if the error message looks like rate-limit JSON
    try {
      const parsed = JSON.parse(message);
      if (parsed.error === "global_limit" || parsed.error === "user_limit") {
        return uiMessages;
      }
    } catch {
      // Not JSON, show as regular error
    }

    return [
      ...uiMessages,
      {
        id: "chat-error",
        role: "assistant" as const,
        content: `Error: ${message}`,
      },
    ];
  }, [error?.message, rateLimitError, submitError, uiMessages]);

  async function handleSubmit() {
    const prompt = input.trim();
    if (!prompt) {
      return;
    }

    setInput("");

    let conversationId = activeConversationId;
    let createdConversationId: string | null = null;
    try {
      setSubmitError(null);
      setRateLimitError(null);

      if (!conversationId) {
        const response = await fetch("/api/conversations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: prompt.slice(0, 60) || "New conversation",
            sessionId: getSessionId() || undefined,
          }),
        });

        if (!response.ok) {
          throw new Error("Failed to create conversation.");
        }

        const conversation = (await response.json()) as { id: string };
        conversationId = conversation.id;
        createdConversationId = conversationId;
        setActiveConversationId(conversationId);
        sessionStorage.setItem("ephemeral_conversation_id", conversationId);
      }

      hadStreamErrorRef.current = false;
      await append(
        {
          role: "user",
          content: prompt,
        },
        {
          body: {
            conversationId,
          },
        },
      );

      // Navigate only after successful append — never on error,
      // because router.refresh() remounts the component and wipes state.
      // hadStreamErrorRef catches errors that flow through onError (e.g. 429)
      // without causing append to throw.
      if (createdConversationId && !hadStreamErrorRef.current) {
        router.replace(`/chat/${createdConversationId}`);
        router.refresh();
      }
    } catch (submitError) {
      // Restore input so the user can retry
      setInput(prompt);

      const detail =
        submitError instanceof Error ? submitError.message : "Failed to send the message.";

      // Detect rate-limit errors from the 429 JSON response
      try {
        const parsed = JSON.parse(detail);
        if (
          parsed.error === "global_limit" ||
          parsed.error === "user_limit"
        ) {
          setRateLimitError({
            type: parsed.error,
            message: parsed.message,
          });
          return;
        }
      } catch {
        // Not JSON — fall through to generic error
      }

      setSubmitError(detail);
    }
  }

  function handleHitlAction(
    hitlId: string,
    actionId: string,
    controlValues: Record<string, unknown>,
    notes?: string,
  ) {
    setResolvedHitlIds((prev) => new Set(prev).add(hitlId));

    const parts = [
      `[HITL Response] hitlId:${hitlId}`,
      `Action: ${actionId}`,
      `Controls: ${JSON.stringify(controlValues)}`,
    ];
    if (notes) parts.push(`Notes: ${notes}`);

    const content = parts.join("\n");
    // Auto-submit the HITL response without polluting the input field
    void append(
      { role: "user", content },
      { body: { conversationId: activeConversationId } },
    );
  }

  function handleUseCaseCards(payload: UseCaseCardsPayload) {
    setUseCaseData(payload);
  }

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <ChatArea
        title={title}
        messages={renderedMessages}
        onPromptSelect={setInput}
        isLoading={status === "submitted" || status === "streaming"}
        onHitlAction={handleHitlAction}
        onUseCaseCards={handleUseCaseCards}
        onOpenDrawer={() => setDrawerOpen(true)}
        resolvedHitlIds={resolvedHitlIds}
        rateLimitError={rateLimitError}
      />
      <ChatInput
        conversationId={initialConversationId}
        value={input}
        onValueChange={setInput}
        onSubmit={handleSubmit}
        isLoading={status === "submitted" || status === "streaming"}
        onOpenDrawer={() => setDrawerOpen(true)}
      />
      <UseCasesDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onSelectPrompt={(prompt) => {
          setInput(prompt);
        }}
        data={useCaseData}
      />
    </div>
  );
}

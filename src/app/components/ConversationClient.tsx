"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useChat } from "ai/react";

import { ChatArea } from "@/app/components/ChatArea";
import { ChatInput } from "@/app/components/ChatInput";
import { UseCasesDrawer } from "@/app/components/UseCasesDrawer";
import type { ChatMessage } from "@/lib/api";
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

  useEffect(() => {
    setActiveConversationId(initialConversationId);
  }, [initialConversationId]);

  const { messages, input, setInput, append, status, error } = useChat({
    api: "/api/chat",
    id: initialConversationId,
    initialMessages: initialMessages.map((message, index) => ({
      id: message.id ?? `${message.role}-${index}`,
      role: message.role,
      content: message.content,
    })),
    body: activeConversationId ? { conversationId: activeConversationId } : undefined,
    onFinish: () => {
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
        .map((message) => ({
          id: message.id,
          role: message.role as ChatMessage["role"],
          content: message.content,
        })),
    [messages],
  );

  const renderedMessages = useMemo(() => {
    const message = submitError ?? error?.message;
    if (!message) {
      return uiMessages;
    }

    return [
      ...uiMessages,
      {
        id: "chat-error",
        role: "assistant" as const,
        content: `Error: ${message}`,
      },
    ];
  }, [error?.message, submitError, uiMessages]);

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

      if (!conversationId) {
        const response = await fetch("/api/conversations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: prompt.slice(0, 60) || "New conversation",
          }),
        });

        if (!response.ok) {
          throw new Error("Failed to create conversation.");
        }

        const conversation = (await response.json()) as { id: string };
        conversationId = conversation.id;
        createdConversationId = conversationId;
        setActiveConversationId(conversationId);
      }

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

      if (createdConversationId) {
        router.replace(`/chat/${createdConversationId}`);
        router.refresh();
      }
    } catch (submitError) {
      setInput(prompt);

      const detail =
        submitError instanceof Error ? submitError.message : "Failed to send the message.";
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

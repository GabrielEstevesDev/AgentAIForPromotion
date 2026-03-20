import { getBackendUrl } from "@/lib/backend";
import type { ChatMessage, ConversationSummary, ConversationTrace } from "@/lib/api";

async function fetchBackend(path: string, init?: RequestInit) {
  const response = await fetch(`${getBackendUrl()}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw new Error(`Backend request failed: ${response.status}`);
  }

  return response;
}

export async function fetchConversations(): Promise<ConversationSummary[]> {
  const response = await fetchBackend("/api/conversations");
  return response.json();
}

export async function fetchConversation(
  conversationId: string,
): Promise<ConversationSummary> {
  const response = await fetchBackend(`/api/conversations/${conversationId}`);
  return response.json();
}

export async function fetchConversationMessages(
  conversationId: string,
): Promise<ChatMessage[]> {
  const response = await fetchBackend(`/api/conversations/${conversationId}/messages`);
  return response.json();
}

export async function fetchConversationTraces(
  conversationId: string,
): Promise<ConversationTrace[]> {
  try {
    const response = await fetchBackend(`/api/conversations/${conversationId}/traces`);
    return response.json();
  } catch {
    return [];
  }
}

export async function fetchMessagesWithTraces(
  conversationId: string,
): Promise<ChatMessage[]> {
  const [messages, traces] = await Promise.all([
    fetchConversationMessages(conversationId),
    fetchConversationTraces(conversationId),
  ]);

  // Build a map of messageId -> trace
  const traceMap = new Map<string, ConversationTrace>();
  for (const t of traces) {
    traceMap.set(t.messageId, t);
  }

  // Attach trace data to matching messages
  return messages.map((msg) => {
    const traceEntry = msg.id ? traceMap.get(msg.id) : undefined;
    if (traceEntry) {
      return { ...msg, trace: traceEntry.trace };
    }
    return msg;
  });
}

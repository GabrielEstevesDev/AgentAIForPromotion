import { getBackendUrl } from "@/lib/backend";
import type { ChatMessage, ConversationSummary } from "@/lib/api";

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

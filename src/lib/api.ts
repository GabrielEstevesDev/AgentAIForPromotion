const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL
  ? `${process.env.NEXT_PUBLIC_BACKEND_URL}/api`
  : "/api";

export type ConversationSummary = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
};

export type ChatMessage = {
  id?: string;
  conversationId?: string;
  role: "user" | "assistant" | "system" | "data";
  content: string;
  createdAt?: string;
};

export async function getConversations(): Promise<ConversationSummary[]> {
  const response = await fetch(`${API_BASE}/conversations`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to load conversations.");
  }

  return response.json();
}

export async function getConversationMessages(
  conversationId: string,
): Promise<ChatMessage[]> {
  const response = await fetch(`${API_BASE}/conversations/${conversationId}/messages`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to load messages.");
  }

  return response.json();
}

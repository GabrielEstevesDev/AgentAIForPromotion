const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL
  ? `${process.env.NEXT_PUBLIC_BACKEND_URL}/api`
  : "/api";

export type ConversationSummary = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
};

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

export type ChatMessage = {
  id?: string;
  conversationId?: string;
  role: "user" | "assistant" | "system" | "data";
  content: string;
  createdAt?: string;
  trace?: TraceEvent[];
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

export type ConversationTrace = {
  messageId: string;
  trace: TraceEvent[];
  createdAt: string;
};

export async function getConversationTraces(
  conversationId: string,
): Promise<ConversationTrace[]> {
  try {
    const response = await fetch(`${API_BASE}/conversations/${conversationId}/traces`, {
      cache: "no-store",
    });

    if (!response.ok) {
      return [];
    }

    return response.json();
  } catch {
    return [];
  }
}

import { ConversationClient } from "@/app/components/ConversationClient";
import { StaleSessionRedirect } from "@/app/components/StaleSessionRedirect";
import { fetchConversation, fetchMessagesWithTraces } from "@/lib/server-api";

type ChatPageProps = {
  params: Promise<{
    id: string;
  }>;
};

export default async function ConversationPage({ params }: ChatPageProps) {
  const { id } = await params;
  const [conversation, messages] = await Promise.all([
    fetchConversation(id).catch(() => null),
    fetchMessagesWithTraces(id).catch(() => []),
  ]);

  if (!conversation) {
    return <StaleSessionRedirect />;
  }

  return (
    <ConversationClient
      key={id}
      initialConversationId={id}
      initialMessages={messages}
      title={conversation.title ?? `Conversation ${id.slice(0, 8)}`}
    />
  );
}

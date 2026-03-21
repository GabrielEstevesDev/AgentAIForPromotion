"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ConversationClient } from "@/app/components/ConversationClient";

export default function NewChatPage() {
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const savedId = sessionStorage.getItem("ephemeral_conversation_id");
    if (savedId) {
      router.replace(`/chat/${savedId}`);
    } else {
      setChecked(true);
    }
  }, [router]);

  if (!checked) {
    return null;
  }

  return <ConversationClient title="New conversation" />;
}

"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function StaleSessionRedirect() {
  const router = useRouter();

  useEffect(() => {
    sessionStorage.removeItem("ephemeral_conversation_id");
    router.replace("/chat");
  }, [router]);

  return null;
}

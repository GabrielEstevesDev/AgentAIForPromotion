"use client";

import { useEffect, useRef, useState } from "react";
import { LayoutGrid, SendHorizontal } from "lucide-react";

type ChatInputProps = {
  conversationId?: string;
  value?: string;
  onValueChange?: (value: string) => void;
  onSubmit?: () => void | Promise<void>;
  isLoading?: boolean;
  onOpenDrawer?: () => void;
};

export function ChatInput({
  conversationId,
  value,
  onValueChange,
  onSubmit,
  isLoading = false,
  onOpenDrawer,
}: ChatInputProps) {
  const [internalValue, setInternalValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const currentValue = value ?? internalValue;

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  }, [currentValue]);

  function updateValue(nextValue: string) {
    onValueChange?.(nextValue);
    if (value === undefined) {
      setInternalValue(nextValue);
    }
  }

  async function submit() {
    const nextValue = currentValue.trim();
    if (!nextValue) {
      return;
    }

    await onSubmit?.();

    if (value === undefined) {
      setInternalValue("");
    }
  }

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 flex justify-center px-4 pb-[max(1.5rem,env(safe-area-inset-bottom))]">
      <div className="pointer-events-auto w-full max-w-3xl rounded-[1.75rem] border border-[var(--border)] bg-[var(--card-strong)] p-3 shadow-[0_20px_60px_-30px_rgba(0,0,0,0.45)] backdrop-blur">
        <div className="flex items-end gap-3">
          {onOpenDrawer && (
            <button
              type="button"
              onClick={onOpenDrawer}
              className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-[var(--muted)] transition hover:bg-[color:color-mix(in_srgb,var(--foreground)_8%,transparent)] hover:text-[var(--foreground)]"
              aria-label="Browse use cases"
            >
              <LayoutGrid size={18} />
            </button>
          )}
          <textarea
            ref={textareaRef}
            rows={1}
            value={currentValue}
            onChange={(event) => updateValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submit();
              }
            }}
            placeholder={
              conversationId
                ? "Reply in this conversation..."
                : "Ask about orders, products, policies, or analytics..."
            }
            className="max-h-32 min-h-12 flex-1 resize-none border-0 bg-transparent px-3 py-3 text-sm text-[var(--foreground)] outline-none placeholder:text-[var(--muted)]"
          />
          <button
            type="button"
            onClick={() => void submit()}
            disabled={!currentValue.trim() || isLoading}
            className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-[var(--accent)] text-white transition hover:bg-[var(--accent-strong)] disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Send message"
          >
            <SendHorizontal size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}

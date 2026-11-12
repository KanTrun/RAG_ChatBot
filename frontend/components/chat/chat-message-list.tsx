"use client";

import { useEffect, useRef } from "react";
import { MessageBubble, type RetrievalDiagnostics } from "./message-bubble";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: any[];
  state?: "streaming" | "complete" | "error";
  loadingModel?: boolean;
  usedOutsideKnowledge?: boolean;
  abstained?: boolean;
  diagnostics?: RetrievalDiagnostics | null;
  latency_ms?: number | null;
  tokens_used?: number | null;
}

interface ChatMessageListProps {
  messages: Message[];
  onCitationClick: (num: number, sources?: any[]) => void;
  onDeleteMessage?: (messageId: string) => void;
  onEditMessage?: (messageId: string, content: string) => void;
  onRegenerateMessage?: (messageId: string) => void;
  onCopyMessage?: (content: string) => void;
  deleteDisabled?: boolean;
}

export function ChatMessageList({
  messages,
  onCitationClick,
  onDeleteMessage,
  onEditMessage,
  onRegenerateMessage,
  onCopyMessage,
  deleteDisabled = false,
}: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const userScrolledUp = useRef(false);
  const previousSnapshot = useRef({
    count: 0,
    lastId: null as string | null,
    lastContentLength: 0,
  });

  useEffect(() => {
    const lastMessage = messages[messages.length - 1];
    const countIncreased = messages.length > previousSnapshot.current.count;
    const streamingExpanded =
      Boolean(lastMessage) &&
      previousSnapshot.current.lastId === lastMessage?.id &&
      (lastMessage?.content.length || 0) > previousSnapshot.current.lastContentLength;

    if (
      !userScrolledUp.current &&
      (countIncreased || streamingExpanded) &&
      typeof bottomRef.current?.scrollIntoView === "function"
    ) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }

    previousSnapshot.current = {
      count: messages.length,
      lastId: lastMessage?.id || null,
      lastContentLength: lastMessage?.content.length || 0,
    };
  }, [messages]);

  function handleScroll() {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
    userScrolledUp.current = !atBottom;
  }

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="flex-1 overflow-y-auto px-4 py-6 scroll-smooth"
      role="log"
      aria-live="polite"
    >
      <div className="mx-auto max-w-3xl space-y-4">
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            onCitationClick={onCitationClick}
            onDelete={onDeleteMessage}
            onEditAndResend={onEditMessage}
            onRegenerate={onRegenerateMessage}
            onCopy={onCopyMessage}
            deleteDisabled={deleteDisabled}
          />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

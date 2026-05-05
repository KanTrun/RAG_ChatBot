"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { FileText, LayoutDashboard, MessageSquare, MessageSquarePlus, PanelLeftClose, PanelLeft } from "lucide-react";
import { apiJson } from "@/lib/client-api";
import { AuthenticatedUserFooter } from "@/components/shared/authenticated-user-footer";

interface Conversation {
  id: string;
  title: string | null;
  updated_at: string;
  message_count: number;
}

interface ChatSidebarProps {
  open: boolean;
  onToggle: () => void;
}

export function ChatSidebar({ open, onToggle }: ChatSidebarProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const searchParams = useSearchParams();
  const { data: session } = useSession();
  const isAdmin = (session?.roles ?? session?.user?.roles ?? []).includes("admin");
  const activeConversationId = searchParams.get("conversationId");

  useEffect(() => {
    apiJson<{ items: Conversation[] }>("/api/v1/conversations")
      .then((data) => setConversations(data.items || []))
      .catch(() => {});
  }, []);

  if (!open) {
    return (
      <div className="flex w-16 flex-col items-center border-r border-border-primary bg-surface-secondary py-4">
        <button
          onClick={onToggle}
          className="rounded-lg p-2 text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
          aria-label="Open sidebar"
        >
          <PanelLeft className="h-5 w-5" />
        </button>
        <div className="mt-4 flex flex-col gap-2">
          <Link
            href="/chat"
            className="rounded-lg p-2 text-accent-primary hover:bg-surface-tertiary"
            aria-label="Chat"
          >
            <MessageSquare className="h-5 w-5" />
          </Link>
          <Link
            href="/documents"
            className="rounded-lg p-2 text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
            aria-label="My documents"
          >
            <FileText className="h-5 w-5" />
          </Link>
          {isAdmin && (
            <Link
              href="/admin"
              className="rounded-lg p-2 text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
              aria-label="Admin dashboard"
            >
              <LayoutDashboard className="h-5 w-5" />
            </Link>
          )}
        </div>
      </div>
    );
  }

  return (
    <aside className="flex w-72 flex-col border-r border-border-primary bg-surface-secondary">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border-primary px-4 py-3">
        <h2 className="text-sm font-semibold text-content-primary">Conversations</h2>
        <div className="flex gap-1">
          <Link
            href="/chat"
            className="rounded-lg p-1.5 text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
            aria-label="New chat"
          >
            <MessageSquarePlus className="h-4 w-4" />
          </Link>
          <button
            onClick={onToggle}
            className="rounded-lg p-1.5 text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
            aria-label="Close sidebar"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="border-b border-border-primary p-2">
        <Link
          href="/chat"
          className="flex items-center gap-2 rounded-lg bg-accent-primary/10 px-3 py-2 text-sm font-medium text-accent-primary"
        >
          <MessageSquare className="h-4 w-4" />
          Chat
        </Link>
        <Link
          href="/documents"
          className="mt-1 flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
        >
          <FileText className="h-4 w-4" />
          My documents
        </Link>
        {isAdmin && (
          <Link
            href="/admin"
            className="mt-1 flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
          >
            <LayoutDashboard className="h-4 w-4" />
            Admin dashboard
          </Link>
        )}
      </div>

      {/* Conversation list */}
      <nav className="flex-1 overflow-y-auto p-2">
        {conversations.length === 0 ? (
          <p className="px-3 py-8 text-center text-xs text-content-tertiary">
            No conversations yet
          </p>
        ) : (
          <ul className="space-y-1">
            {conversations.map((conv) => (
              <li key={conv.id}>
                <Link
                  href={`/chat?conversationId=${conv.id}`}
                  className={`group relative block overflow-hidden rounded-xl border px-3 py-3 text-left text-sm transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/50 ${
                    activeConversationId === conv.id
                      ? "border-accent-primary/30 bg-accent-primary/10 text-accent-primary shadow-[0_12px_30px_rgba(99,102,241,0.18)]"
                      : "border-transparent text-content-secondary hover:-translate-y-0.5 hover:border-white/8 hover:bg-white/[0.04] hover:text-content-primary hover:shadow-[0_16px_36px_rgba(0,0,0,0.22)]"
                  }`}
                  aria-current={activeConversationId === conv.id ? "page" : undefined}
                >
                  <span
                    className={`pointer-events-none absolute inset-y-3 left-1 w-1 rounded-full transition-opacity ${
                      activeConversationId === conv.id
                        ? "bg-accent-primary opacity-100"
                        : "bg-accent-primary/80 opacity-0 group-hover:opacity-100"
                    }`}
                  />
                  <div className="flex items-start gap-3 pl-3">
                    <span
                      className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border transition-colors ${
                        activeConversationId === conv.id
                          ? "border-accent-primary/20 bg-accent-primary/15 text-accent-primary"
                          : "border-white/6 bg-black/10 text-content-tertiary group-hover:border-accent-primary/10 group-hover:text-content-secondary"
                      }`}
                    >
                      <MessageSquare className="h-4 w-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-3">
                        <span className="block truncate font-medium">
                          {conv.title || "New Chat"}
                        </span>
                        <span
                          className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors ${
                            activeConversationId === conv.id
                              ? "border-accent-primary/20 bg-accent-primary/10 text-accent-primary"
                              : "border-white/8 bg-black/10 text-content-tertiary group-hover:border-white/12 group-hover:text-content-secondary"
                          }`}
                        >
                          {conv.message_count} msgs
                        </span>
                      </div>
                      <span
                        className={`mt-1 block truncate text-xs transition-colors ${
                          activeConversationId === conv.id
                            ? "text-accent-primary/80"
                            : "text-content-tertiary group-hover:text-content-secondary"
                        }`}
                      >
                        {activeConversationId === conv.id
                          ? "Current conversation"
                          : "Open conversation"}
                      </span>
                    </div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </nav>
      <div className="border-t border-border-primary p-3">
        <AuthenticatedUserFooter />
      </div>
    </aside>
  );
}

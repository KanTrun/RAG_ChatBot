"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import {
  FileText,
  LayoutDashboard,
  MessageSquare,
  MessageSquarePlus,
  PencilLine,
  PanelLeft,
  PanelLeftClose,
  Trash2,
} from "lucide-react";
import { apiJson, getApiErrorMessage } from "@/lib/client-api";
import { AuthenticatedUserFooter } from "@/components/shared/authenticated-user-footer";
import { OverflowActionMenu } from "./overflow-action-menu";

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
  const [conversationError, setConversationError] = useState("");
  const [deletingConversationId, setDeletingConversationId] = useState<string | null>(null);
  const [renamingConversationId, setRenamingConversationId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [savingConversationId, setSavingConversationId] = useState<string | null>(null);
  const [streamingConversationId, setStreamingConversationId] = useState<string | null>(null);
  const renameRequestVersionRef = useRef(0);
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: session } = useSession();
  const isAdmin = (session?.roles ?? session?.user?.roles ?? []).includes("admin");
  const activeConversationId = searchParams.get("conversationId");

  const loadConversations = useCallback(() => {
    apiJson<{ items: Conversation[] }>("/api/v1/conversations")
      .then((data) => setConversations(data.items || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    function handleConversationChange() {
      loadConversations();
    }

    window.addEventListener("chat-conversations-changed", handleConversationChange);
    return () => {
      window.removeEventListener("chat-conversations-changed", handleConversationChange);
    };
  }, [loadConversations]);

  useEffect(() => {
    function handleStreamStatus(event: Event) {
      const detail = (event as CustomEvent<{ conversationId?: string | null; active?: boolean }>).detail;
      if (!detail?.active) {
        setStreamingConversationId(null);
        return;
      }
      setStreamingConversationId(detail.conversationId || null);
    }

    window.addEventListener("chat-stream-status", handleStreamStatus as EventListener);
    return () => {
      window.removeEventListener("chat-stream-status", handleStreamStatus as EventListener);
    };
  }, []);

  const handleDeleteConversation = useCallback(
    async (conversationId: string, title: string | null) => {
      const confirmed = window.confirm(
        `Delete "${title || "New Chat"}" permanently? This cannot be undone.`,
      );
      if (!confirmed) return;

      setConversationError("");
      setDeletingConversationId(conversationId);
      try {
        await apiJson<void>(`/api/v1/conversations/${conversationId}`, {
          method: "DELETE",
        });
        setConversations((current) => current.filter((item) => item.id !== conversationId));
        window.dispatchEvent(new Event("chat-conversations-changed"));
        if (activeConversationId === conversationId) {
          router.replace("/chat");
        }
      } catch (error) {
        setConversationError(getApiErrorMessage(error));
      } finally {
        setDeletingConversationId(null);
      }
    },
    [activeConversationId, router],
  );

  const handleRenameStart = useCallback((conversation: Conversation) => {
    setConversationError("");
    setRenamingConversationId(conversation.id);
    setRenameValue(conversation.title || "");
  }, []);

  const handleRenameCancel = useCallback(() => {
    setRenamingConversationId(null);
    setRenameValue("");
  }, []);

  const handleRenameSubmit = useCallback(
    async (conversationId: string) => {
      setConversationError("");
      setSavingConversationId(conversationId);
      const nextTitle = renameValue.trim();
      const nextRequestVersion = renameRequestVersionRef.current + 1;
      renameRequestVersionRef.current = nextRequestVersion;
      const previousConversation = conversations.find((item) => item.id === conversationId);

      setConversations((current) =>
        current.map((item) =>
          item.id === conversationId ? { ...item, title: nextTitle || null } : item,
        ),
      );

      try {
        const response = await apiJson<Conversation>(`/api/v1/conversations/${conversationId}`, {
          method: "PATCH",
          body: JSON.stringify({ title: nextTitle || null }),
        });
        if (renameRequestVersionRef.current !== nextRequestVersion) {
          return;
        }
        setConversations((current) =>
          current.map((item) =>
            item.id === conversationId
              ? { ...item, title: response.title, updated_at: response.updated_at }
              : item,
          ),
        );
        setRenamingConversationId(null);
        setRenameValue("");
        window.dispatchEvent(new Event("chat-conversations-changed"));
      } catch (error) {
        if (renameRequestVersionRef.current !== nextRequestVersion) {
          return;
        }
        setConversations((current) =>
          current.map((item) =>
            item.id === conversationId
              ? { ...item, title: previousConversation?.title ?? item.title }
              : item,
          ),
        );
        setConversationError(getApiErrorMessage(error));
      } finally {
        if (renameRequestVersionRef.current === nextRequestVersion) {
          setSavingConversationId(null);
        }
      }
    },
    [conversations, renameValue],
  );

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
        {conversationError && (
          <p role="alert" className="px-3 pb-2 text-xs text-red-400">
            Conversation update failed: {conversationError}
          </p>
        )}
        {conversations.length === 0 ? (
          <p className="px-3 py-8 text-center text-xs text-content-tertiary">
            No conversations yet
          </p>
        ) : (
          <ul className="space-y-1">
            {conversations.map((conv) => (
              <li key={conv.id}>
                {(() => {
                  const actionDisabled =
                    deletingConversationId === conv.id ||
                    savingConversationId === conv.id ||
                    streamingConversationId === conv.id;
                  return (
                <div className="flex items-stretch gap-2">
                  {renamingConversationId === conv.id ? (
                    <div
                      className={`relative flex-1 overflow-hidden rounded-xl border px-3 py-3 text-left text-sm ${
                        activeConversationId === conv.id
                          ? "border-accent-primary/30 bg-accent-primary/10 text-accent-primary shadow-[0_12px_30px_rgba(99,102,241,0.18)]"
                          : "border-white/8 bg-white/[0.04] text-content-primary"
                      }`}
                    >
                      <div className="flex items-start gap-3 pl-3">
                        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-accent-primary/20 bg-accent-primary/15 text-accent-primary">
                          <PencilLine className="h-4 w-4" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <input
                            autoFocus
                            value={renameValue}
                            onChange={(event) => setRenameValue(event.target.value)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter") {
                                event.preventDefault();
                                void handleRenameSubmit(conv.id);
                              }
                              if (event.key === "Escape") {
                                event.preventDefault();
                                handleRenameCancel();
                              }
                            }}
                            className="w-full rounded-xl border border-accent-primary/20 bg-surface-primary px-3 py-2 text-sm text-content-primary outline-none ring-0 transition-colors focus:border-accent-primary"
                            aria-label={`Rename conversation ${conv.title || "New Chat"}`}
                          />
                          <div className="mt-2 flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => void handleRenameSubmit(conv.id)}
                              disabled={savingConversationId === conv.id}
                              className="rounded-xl bg-accent-primary px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-accent-primary-hover disabled:opacity-50"
                            >
                              Lưu
                            </button>
                            <button
                              type="button"
                              onClick={handleRenameCancel}
                              disabled={savingConversationId === conv.id}
                              className="rounded-xl border border-border-primary px-3 py-2 text-xs font-medium text-content-secondary transition-colors hover:bg-surface-tertiary hover:text-content-primary disabled:opacity-50"
                            >
                              Hủy
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <Link
                      href={`/chat?conversationId=${conv.id}`}
                      className={`group relative block flex-1 overflow-hidden rounded-xl border px-3 py-3 text-left text-sm transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/50 ${
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
                  )}
                  <OverflowActionMenu
                    buttonLabel={`Mở menu đoạn chat ${conv.title || "New Chat"}`}
                    items={[
                      {
                        label: "Đổi tên đoạn chat",
                        icon: PencilLine,
                        disabled: actionDisabled,
                        onSelect: () => handleRenameStart(conv),
                      },
                      {
                        label: "Xóa đoạn chat",
                        icon: Trash2,
                        destructive: true,
                        disabled: actionDisabled,
                        onSelect: () => void handleDeleteConversation(conv.id, conv.title),
                      },
                    ]}
                    disabled={actionDisabled}
                  />
                </div>
                  );
                })()}
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

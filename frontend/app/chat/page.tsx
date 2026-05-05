"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import {
  ActiveDocumentContextBar,
  type ActiveDocument,
} from "@/components/chat/active-document-context-bar";
import { ChatInput } from "@/components/chat/chat-input";
import { ChatMessageList } from "@/components/chat/chat-message-list";
import { SourcesPanel } from "@/components/chat/sources-panel";
import { ApiError, apiFetch, apiJson, getApiErrorMessage } from "@/lib/client-api";
import { type UploadedDocument } from "@/lib/document-upload";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  state?: "streaming" | "complete" | "error";
}

interface Source {
  citation_number: number;
  document_title: string;
  file_name: string;
  page_number: number | null;
  section: string | null;
  section_path?: string | null;
  block_type?: string | null;
  page_start?: number | null;
  page_end?: number | null;
  parent_block_id?: string | null;
  heading_level?: number | null;
  ingestion_version?: string | null;
  score: number;
  excerpt?: string | null;
  selection_reason?: string | null;
  answer_section?: string | null;
  coverage_labels?: string[] | null;
}

interface ConversationDetails {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
  active_documents: ActiveDocument[];
}

type ChatResponseMode = "strict_documents" | "hybrid_general";

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function buildUploadNotice(document: UploadedDocument) {
  const statusLine = {
    pending: "Indexing is queued. It will stay active for this chat and become searchable as soon as indexing completes.",
    processing: "Indexing is in progress. It stays active for this chat while processing finishes.",
    indexed: "Indexing is complete. It is now active for this chat and ready for grounded answers.",
    failed: "Indexing failed. Re-index or re-upload it from the documents screen before asking about it.",
  }[document.status];

  if (document.duplicate_of_existing) {
    return `${document.file_name} is already in your document library and is now attached to this chat. Current status: ${statusLine}`;
  }

  return `Uploaded ${document.file_name} (${document.file_type.toUpperCase()}, ${formatFileSize(document.file_size)}). ${statusLine}`;
}

function dedupeDocuments(documents: ActiveDocument[]) {
  const seen = new Set<string>();
  const unique: ActiveDocument[] = [];
  for (const document of documents) {
    if (seen.has(document.id)) continue;
    seen.add(document.id);
    unique.push(document);
  }
  return unique;
}

function toActiveDocument(document: UploadedDocument): ActiveDocument {
  return {
    id: document.id,
    title: document.title,
    file_name: document.file_name,
    status: document.status,
    total_chunks: document.total_chunks,
  };
}

function parseDocumentIdsParam(rawValue: string | null) {
  if (!rawValue) return [];
  return rawValue
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

function collectDeletedMessageIds(messages: Message[], targetMessageId: string) {
  const targetIndex = messages.findIndex((message) => message.id === targetMessageId);
  if (targetIndex === -1) return [];

  const target = messages[targetIndex];
  const deletedIds = new Set<string>([target.id]);
  if (target.role === "user") {
    const nextMessage = messages[targetIndex + 1];
    if (nextMessage?.role === "assistant") {
      deletedIds.add(nextMessage.id);
    }
  } else {
    const previousMessage = messages[targetIndex - 1];
    if (previousMessage?.role === "user") {
      deletedIds.add(previousMessage.id);
    }
  }

  return Array.from(deletedIds);
}

function findPreviousUserMessage(messages: Message[], assistantMessageId: string) {
  const targetIndex = messages.findIndex((message) => message.id === assistantMessageId);
  if (targetIndex <= 0) return null;
  const previous = messages[targetIndex - 1];
  return previous?.role === "user" ? previous : null;
}

function ChatPageContent() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [activeDocuments, setActiveDocuments] = useState<ActiveDocument[]>([]);
  const [activeDocumentSyncError, setActiveDocumentSyncError] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [activeCitation, setActiveCitation] = useState<number | null>(null);
  const [responseMode, setResponseMode] =
    useState<ChatResponseMode>("strict_documents");
  const [composerDraft, setComposerDraft] = useState("");
  const [composerMode, setComposerMode] = useState<
    { kind: "new" } | { kind: "edit" | "regenerate"; targetMessageId: string }
  >({ kind: "new" });
  const [messageDeleteError, setMessageDeleteError] = useState("");
  const [messageActionError, setMessageActionError] = useState("");
  const [messageActionNotice, setMessageActionNotice] = useState("");
  const [deletingMessageId, setDeletingMessageId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const activeDocumentSyncChainRef = useRef<Promise<void>>(Promise.resolve());
  const messageMutationVersionRef = useRef(0);
  const router = useRouter();
  const replaceRoute = router.replace;
  const searchParams = useSearchParams();
  const { data: session } = useSession();
  const sessionInvalid = session?.error === "RefreshAccessTokenError";
  const selectedConversationId = searchParams.get("conversationId");
  const selectedDocumentIdsParam = searchParams.get("documentIds");
  const selectedDocumentIds = parseDocumentIdsParam(selectedDocumentIdsParam);

  const queueActiveDocumentSync = useCallback(
    (nextDocuments: ActiveDocument[]) => {
      setActiveDocuments(nextDocuments);
      setActiveDocumentSyncError("");

      if (!conversationId) return;

      activeDocumentSyncChainRef.current = activeDocumentSyncChainRef.current
        .catch(() => undefined)
        .then(async () => {
          const requestedIds = nextDocuments.map((document) => document.id);
          try {
            const response = await apiJson<ConversationDetails>(`/api/v1/conversations/${conversationId}`, {
              method: "PATCH",
              body: JSON.stringify({ document_ids: requestedIds }),
            });
            setActiveDocuments((current) => {
              const currentIds = current.map((document) => document.id);
              return currentIds.join("|") === requestedIds.join("|")
                ? response.active_documents || []
                : current;
            });
            setActiveDocumentSyncError("");
          } catch (error) {
            setActiveDocumentSyncError(getApiErrorMessage(error));
          }
        });
    },
    [conversationId],
  );

  useEffect(() => {
    const nextConversationId = selectedConversationId?.trim() || null;
    abortRef.current?.abort();
    abortRef.current = null;
    setIsLoading(false);
    setActiveDocumentSyncError("");
    setMessageDeleteError("");
    setMessageActionError("");
    setMessageActionNotice("");
    setSources([]);
    setSourcesOpen(false);
    setActiveCitation(null);
    setComposerMode({ kind: "new" });
    setComposerDraft("");

    if (!nextConversationId) {
      setConversationId(null);
      setMessages([]);
      if (selectedDocumentIds.length === 0) {
        setActiveDocuments([]);
        return;
      }

      let cancelled = false;
      void Promise.all(
        selectedDocumentIds.map((documentId) =>
          apiJson<ActiveDocument>(`/api/v1/documents/${documentId}`),
        ),
      )
        .then((documents) => {
          if (cancelled) return;
          setActiveDocuments(dedupeDocuments(documents));
        })
        .catch((error) => {
          if (cancelled) return;
          setActiveDocuments([]);
          setMessages([
            {
              id: crypto.randomUUID(),
              role: "assistant",
              content: getApiErrorMessage(error),
            },
          ]);
        });

      return () => {
        cancelled = true;
      };
    }

    let cancelled = false;
    setConversationId(nextConversationId);
    const hydrationMutationVersion = messageMutationVersionRef.current;

    void Promise.all([
      apiJson<Message[]>(`/api/v1/conversations/${nextConversationId}/messages`),
      apiJson<ConversationDetails>(`/api/v1/conversations/${nextConversationId}`),
    ])
      .then(([history, conversation]) => {
        if (cancelled) return;
        setMessages((current) =>
          messageMutationVersionRef.current === hydrationMutationVersion ? history : current,
        );
        setActiveDocuments(conversation.active_documents || []);
      })
      .catch((error) => {
        if (cancelled) return;
        setConversationId(null);
        setActiveDocuments([]);
        if (error instanceof ApiError && error.status === 404) {
          setMessages([]);
          replaceRoute("/chat");
          return;
        }
        setMessages([
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: getApiErrorMessage(error),
          },
        ]);
      });

    return () => {
      cancelled = true;
    };
  }, [replaceRoute, selectedConversationId, selectedDocumentIdsParam]);

  const handleSend = useCallback(
    async (query: string, requestedResponseMode: ChatResponseMode) => {
      if (!query.trim() || isLoading) return;

      const replacementMode = composerMode.kind === "new" ? null : composerMode;
      const replacementDeletedIds =
        replacementMode && conversationId
          ? collectDeletedMessageIds(messages, replacementMode.targetMessageId)
          : [];
      const replacementSnapshot =
        replacementMode && conversationId && replacementDeletedIds.length > 0
          ? {
              previousMessages: messages,
              previousSources: sources,
              previousSourcesOpen: sourcesOpen,
              previousActiveCitation: activeCitation,
              previousComposerMode: replacementMode,
            }
          : null;

      if (replacementMode && !replacementSnapshot) {
        setComposerMode({ kind: "new" });
      }

      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: query,
      };
      const assistantMessageId = crypto.randomUUID();
      const assistantPlaceholder: Message = {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        state: "streaming",
      };
      messageMutationVersionRef.current += 1;
      setMessages((current) => {
        const baseMessages = replacementDeletedIds.length
          ? current.filter((message) => !replacementDeletedIds.includes(message.id))
          : current;
        return [...baseMessages, userMessage, assistantPlaceholder];
      });
      setIsLoading(true);
      setDeletingMessageId(replacementMode?.targetMessageId ?? null);
      setSources([]);
      setMessageDeleteError("");
      setMessageActionError("");
      setMessageActionNotice("");
      setSourcesOpen(false);
      setActiveCitation(null);
      setComposerMode({ kind: "new" });
      setComposerDraft("");
      window.dispatchEvent(
        new CustomEvent("chat-stream-status", {
          detail: { conversationId, active: true },
        }),
      );

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await apiFetch("/api/v1/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query,
            conversation_id: conversationId,
            replace_message_id: replacementSnapshot?.previousComposerMode.targetMessageId ?? null,
            document_ids: activeDocuments.map((document) => document.id),
            response_mode: requestedResponseMode,
          }),
          signal: controller.signal,
        });

        if (!res.ok) {
          let detail = "Chat request failed";
          try {
            const payload = await res.json();
            if (typeof payload.detail === "string") {
              detail = payload.detail;
            }
          } catch {
            // keep default detail
          }
          throw new Error(detail);
        }

        const reader = res.body?.getReader();
        if (!reader) throw new Error("No response body");

        const decoder = new TextDecoder();
        let aiContent = "";

        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const json = line.slice(6).trim();
            if (!json) continue;

            let event: any;
            try {
              event = JSON.parse(json);
            } catch {
              // skip malformed SSE
              continue;
            }

            if (event.type === "chunk" && event.content) {
              aiContent += event.content;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMessageId
                    ? { ...m, content: aiContent, state: "streaming" }
                    : m
                )
              );
            } else if (event.type === "sources" && event.sources) {
              setSources(event.sources);
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMessageId
                    ? { ...m, sources: event.sources }
                    : m
                )
              );
            } else if (event.type === "done") {
              if (Array.isArray(event.active_documents)) {
                setActiveDocuments(event.active_documents);
              }
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id === userMessage.id) {
                    return event.user_message_id ? { ...m, id: event.user_message_id } : m;
                  }
                  if (m.id === assistantMessageId) {
                    return {
                      ...m,
                      id: event.message_id || m.id,
                      state: "complete",
                    };
                  }
                  return m;
                }),
              );
              if (!conversationId && event.conversation_id) {
                setConversationId(event.conversation_id);
                router.replace(`/chat?conversationId=${event.conversation_id}`);
              }
              window.dispatchEvent(new Event("chat-conversations-changed"));
            } else if (event.type === "error" && event.content) {
              throw new Error(event.content);
            }
          }
        }
      } catch (err: unknown) {
        if (!(err instanceof Error && err.name === "AbortError")) {
          if (replacementSnapshot) {
            setMessages(replacementSnapshot.previousMessages);
            setSources(replacementSnapshot.previousSources);
            setSourcesOpen(replacementSnapshot.previousSourcesOpen);
            setActiveCitation(replacementSnapshot.previousActiveCitation);
            setComposerMode(replacementSnapshot.previousComposerMode);
            setComposerDraft(query);
            setMessageActionError(getApiErrorMessage(err));
          } else {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMessageId
                  ? {
                      ...m,
                      content: getApiErrorMessage(err),
                      state: "error",
                    }
                  : m
              ),
            );
          }
        }
      } finally {
        setIsLoading(false);
        setDeletingMessageId(null);
        abortRef.current = null;
        window.dispatchEvent(
          new CustomEvent("chat-stream-status", {
            detail: { conversationId, active: false },
          }),
        );
      }
    },
    [
      activeCitation,
      activeDocuments,
      composerMode,
      conversationId,
      isLoading,
      messages,
      router,
      sources,
      sourcesOpen,
    ],
  );

  const handleCitationClick = useCallback((num: number, citationSources?: Source[]) => {
    setActiveCitation(num);
    if (citationSources?.length) {
      setSources(citationSources);
    }
    setSourcesOpen(true);
  }, []);

  const handleUploadComplete = useCallback(
    (document: UploadedDocument) => {
      messageMutationVersionRef.current += 1;
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: buildUploadNotice(document),
        },
      ]);
    },
    [],
  );

  const handleUploadStatusChange = useCallback(
    (document: UploadedDocument) => {
      const nextDocument = toActiveDocument(document);
      const nextDocuments = dedupeDocuments([
        ...activeDocuments.filter((item) => item.id !== document.id),
        nextDocument,
      ]);
      queueActiveDocumentSync(nextDocuments);
    },
    [activeDocuments, queueActiveDocumentSync],
  );

  const handleRemoveActiveDocument = useCallback(
    (documentId: string) => {
      const nextDocuments = activeDocuments.filter((document) => document.id !== documentId);
      queueActiveDocumentSync(nextDocuments);
    },
    [activeDocuments, queueActiveDocumentSync],
  );

  const handleClearActiveDocuments = useCallback(() => {
    queueActiveDocumentSync([]);
  }, [queueActiveDocumentSync]);

  const handleDeleteMessage = useCallback(
    async (messageId: string) => {
      if (!conversationId) return;

      const deletedIds = collectDeletedMessageIds(messages, messageId);
      if (deletedIds.length === 0) return;

      const confirmed = window.confirm(
        "Delete this chat exchange permanently? This cannot be undone.",
      );
      if (!confirmed) return;

      const previousMessages = messages;
      const previousSources = sources;
      const previousSourcesOpen = sourcesOpen;
      const previousActiveCitation = activeCitation;

      setMessageDeleteError("");
      setMessageActionError("");
      setDeletingMessageId(messageId);
      messageMutationVersionRef.current += 1;
      setMessages((current) => current.filter((message) => !deletedIds.includes(message.id)));
      setSources([]);
      setSourcesOpen(false);
      setActiveCitation(null);

      try {
        await apiJson<void>(
          `/api/v1/conversations/${conversationId}/messages/${messageId}`,
          { method: "DELETE" },
        );
        window.dispatchEvent(new Event("chat-conversations-changed"));
      } catch (error) {
        setMessages(previousMessages);
        setSources(previousSources);
        setSourcesOpen(previousSourcesOpen);
        setActiveCitation(previousActiveCitation);
        setMessageDeleteError(getApiErrorMessage(error));
      } finally {
        setDeletingMessageId(null);
      }
    },
    [activeCitation, conversationId, messages, sources, sourcesOpen],
  );

  const handleEditMessage = useCallback((messageId: string, content: string) => {
    setMessageDeleteError("");
    setMessageActionError("");
    setComposerMode({ kind: "edit", targetMessageId: messageId });
    setComposerDraft(content);
    setMessageActionNotice("");
  }, []);

  const handleRegenerateMessage = useCallback(
    (messageId: string) => {
      setMessageDeleteError("");
      const previousUserMessage = findPreviousUserMessage(messages, messageId);
      if (!previousUserMessage) {
        setMessageActionError("Could not find the user prompt for this answer.");
        return;
      }

      setMessageActionError("");
      setComposerMode({ kind: "regenerate", targetMessageId: messageId });
      setComposerDraft(previousUserMessage.content);
      setMessageActionNotice("");
    },
    [messages],
  );

  const handleCopyMessage = useCallback(async (content: string) => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(content);
      } else {
        throw new Error("Clipboard is not available in this browser.");
      }
      setMessageDeleteError("");
      setMessageActionError("");
      setMessageActionNotice("Đã sao chép câu trả lời vào clipboard.");
    } catch (error) {
      setMessageActionNotice("");
      setMessageActionError(getApiErrorMessage(error));
    }
  }, []);

  // Keyboard shortcut: / or Ctrl+K to focus input
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (
        (e.key === "/" || (e.ctrlKey && e.key === "k")) &&
        !["INPUT", "TEXTAREA"].includes((e.target as HTMLElement).tagName)
      ) {
        e.preventDefault();
        document.getElementById("chat-input")?.focus();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Chat area */}
      <div className="flex flex-1 flex-col">
        {messages.length === 0 ? (
          <div className="flex flex-1 items-center justify-center">
            <div className="text-center">
              <h2 className="text-xl font-semibold text-content-primary">
                Start a conversation
              </h2>
              <p className="mt-2 text-sm text-content-secondary">
                {activeDocuments.length > 0
                  ? `Ask about the ${activeDocuments.length === 1 ? "selected document" : "selected documents"}. This conversation will stay scoped to them until you clear the context.`
                  : responseMode === "strict_documents"
                    ? "Document-only mode is on. Answers will abstain when the current document context is not enough."
                    : "Hybrid mode is on. The assistant will use document evidence first, then outside knowledge when needed."}
              </p>
            </div>
          </div>
        ) : (
          <ChatMessageList
            messages={messages}
            onCitationClick={handleCitationClick}
            onDeleteMessage={handleDeleteMessage}
            onEditMessage={handleEditMessage}
            onRegenerateMessage={handleRegenerateMessage}
            onCopyMessage={handleCopyMessage}
            deleteDisabled={!conversationId || isLoading || sessionInvalid || deletingMessageId !== null}
          />
        )}

        <ActiveDocumentContextBar
          documents={activeDocuments}
          disabled={isLoading || sessionInvalid}
          onRemove={handleRemoveActiveDocument}
          onClear={handleClearActiveDocuments}
        />

        {sessionInvalid && (
          <p role="alert" className="px-4 py-2 text-center text-sm text-red-400">
            Session expired. Please sign in again.
          </p>
        )}
        {activeDocumentSyncError && (
          <p role="alert" className="px-4 pb-2 text-center text-xs text-red-400">
            Failed to sync active documents for this conversation: {activeDocumentSyncError}
          </p>
        )}
        {messageDeleteError && (
          <p role="alert" className="px-4 pb-2 text-center text-xs text-red-400">
            Failed to delete message: {messageDeleteError}
          </p>
        )}
        {messageActionError && (
          <p role="alert" className="px-4 pb-2 text-center text-xs text-red-400">
            Message action failed: {messageActionError}
          </p>
        )}
        {messageActionNotice && (
          <p role="status" className="px-4 pb-2 text-center text-xs text-accent-citation">
            {messageActionNotice}
          </p>
        )}
        <ChatInput
          onSend={handleSend}
          disabled={isLoading || sessionInvalid}
          onUploadComplete={handleUploadComplete}
          onUploadStatusChange={handleUploadStatusChange}
          responseMode={responseMode}
          onResponseModeChange={setResponseMode}
          draftValue={composerDraft}
          onDraftValueChange={setComposerDraft}
          editLabel={
            composerMode.kind === "edit"
              ? "Đang sửa câu hỏi"
              : composerMode.kind === "regenerate"
                ? "Đang tạo lại câu trả lời từ câu hỏi gần nhất"
                : null
          }
          onCancelEdit={() => {
            setMessageDeleteError("");
            setMessageActionError("");
            setMessageActionNotice("");
            setComposerMode({ kind: "new" });
            setComposerDraft("");
          }}
        />
      </div>

      {/* Sources panel */}
      {sourcesOpen && (
        <SourcesPanel
          sources={sources}
          activeCitation={activeCitation}
          onClose={() => setSourcesOpen(false)}
        />
      )}
    </div>
  );
}

export default function ChatPage() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-content-tertiary" suppressHydrationWarning>
        Loading conversation...
      </div>
    );
  }

  return (
    <Suspense fallback={<div className="flex flex-1 items-center justify-center text-sm text-content-tertiary">Loading conversation...</div>}>
      <ChatPageContent />
    </Suspense>
  );
}

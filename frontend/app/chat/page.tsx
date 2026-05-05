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
import { apiFetch, apiJson, getApiErrorMessage } from "@/lib/client-api";
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
  score: number;
  excerpt?: string | null;
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
  const abortRef = useRef<AbortController | null>(null);
  const activeDocumentSyncChainRef = useRef<Promise<void>>(Promise.resolve());
  const router = useRouter();
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
    setSources([]);
    setSourcesOpen(false);
    setActiveCitation(null);

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

    void Promise.all([
      apiJson<Message[]>(`/api/v1/conversations/${nextConversationId}/messages`),
      apiJson<ConversationDetails>(`/api/v1/conversations/${nextConversationId}`),
    ])
      .then(([history, conversation]) => {
        if (cancelled) return;
        setMessages(history);
        setActiveDocuments(conversation.active_documents || []);
      })
      .catch((error) => {
        if (cancelled) return;
        setConversationId(null);
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
  }, [selectedConversationId, selectedDocumentIdsParam]);

  const handleSend = useCallback(
    async (query: string, requestedResponseMode: ChatResponseMode) => {
      if (!query.trim() || isLoading) return;

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
      setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);
      setIsLoading(true);
      setSources([]);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await apiFetch("/api/v1/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query,
            conversation_id: conversationId,
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
              if (event.message_id) {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMessageId
                      ? { ...m, id: event.message_id, state: "complete" }
                      : m
                  )
                );
              } else {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMessageId ? { ...m, state: "complete" } : m
                  )
                );
              }
              if (!conversationId && event.conversation_id) {
                setConversationId(event.conversation_id);
                router.replace(`/chat?conversationId=${event.conversation_id}`);
              }
            } else if (event.type === "error" && event.content) {
              throw new Error(event.content);
            }
          }
        }
      } catch (err: unknown) {
        if (!(err instanceof Error && err.name === "AbortError")) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMessageId
                ? {
                    ...m,
                    content: getApiErrorMessage(err),
                    state: "error",
                  }
                : m
            )
          );
        }
      } finally {
        setIsLoading(false);
        abortRef.current = null;
      }
    },
    [activeDocuments, conversationId, isLoading, router]
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
        <ChatInput
          onSend={handleSend}
          disabled={isLoading || sessionInvalid}
          onUploadComplete={handleUploadComplete}
          onUploadStatusChange={handleUploadStatusChange}
          responseMode={responseMode}
          onResponseModeChange={setResponseMode}
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

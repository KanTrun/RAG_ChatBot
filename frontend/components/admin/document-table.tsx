"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Eye,
  MessageSquare,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Trash2,
  X,
} from "lucide-react";
import { StatusBadge } from "@/components/shared/status-badge";
import { apiJson, getApiErrorMessage } from "@/lib/client-api";
import {
  formatDocumentSize,
  getDocumentBasePath,
  getDocumentStatusDescription,
  type Document,
  type DocumentListResponse,
  type DocumentTableProps,
} from "@/components/admin/document-table-helpers";

interface ChunkItem {
  id: string;
  chunk_index: number;
  content: string;
  page_number: number | null;
  section: string | null;
  section_path: string | null;
  block_type: string | null;
  token_count: number;
}

interface DocumentChunksPayload {
  document_id: string;
  title: string;
  file_name: string;
  chunk_size: number;
  chunk_overlap: number;
  total_chunks: number;
  sections: string[];
  chunks: ChunkItem[];
}

export function DocumentTable({
  mode = "user",
  title = "Documents",
  onChanged,
  onStartChat,
}: DocumentTableProps) {
  const [docs, setDocs] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState("");
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [chunkSize, setChunkSize] = useState(512);
  const [chunkOverlap, setChunkOverlap] = useState(51);
  const [showReindexConfig, setShowReindexConfig] = useState(false);
  const [inspectingChunks, setInspectingChunks] = useState<DocumentChunksPayload | null>(null);
  const [loadingChunksId, setLoadingChunksId] = useState<string | null>(null);
  const requestIdRef = useRef(0);
  const pageSize = 20;
  const canStartChat = mode === "user" && typeof onStartChat === "function";

  const loadDocuments = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (search) params.set("search", search);
    if (statusFilter) params.set("status_filter", statusFilter);

    const basePath = getDocumentBasePath(mode);
    setError("");
    return apiJson<DocumentListResponse>(`${basePath}?${params}`)
      .then((data) => {
        if (requestId !== requestIdRef.current) return;
        setDocs(data.items || []);
        setTotal(data.total || 0);
      })
      .catch((err) => {
        if (requestId === requestIdRef.current) {
          setError(getApiErrorMessage(err));
        }
      });
  }, [mode, page, search, statusFilter]);

  useEffect(() => {
    setSelectedDocumentIds((current) =>
      current.filter((documentId) => docs.some((doc) => doc.id === documentId && doc.status === "indexed")),
    );
  }, [docs]);

  useEffect(() => {
    void loadDocuments();
    return () => {
      requestIdRef.current += 1;
    };
  }, [loadDocuments]);

  useEffect(() => {
    if (!docs.some((doc) => doc.status === "pending" || doc.status === "processing")) {
      return;
    }

    const timer = window.setInterval(() => {
      void loadDocuments();
    }, 4000);

    return () => window.clearInterval(timer);
  }, [docs, loadDocuments]);

  const totalPages = Math.ceil(total / pageSize);

  async function handleDelete(id: string) {
    if (!confirm("Delete this document and all its chunks?")) return;
    const basePath = getDocumentBasePath(mode);
    try {
      await apiJson<void>(`${basePath}/${id}`, { method: "DELETE" });
      setDocs((prev) => prev.filter((d) => d.id !== id));
      setTotal((t) => Math.max(0, t - 1));
      if (inspectingChunks?.document_id === id) {
        setInspectingChunks(null);
      }
      onChanged?.();
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  }

  async function handleReindex(id: string) {
    const basePath = getDocumentBasePath(mode);
    try {
      const options: RequestInit = { method: "POST" };
      if (showReindexConfig) {
        options.body = JSON.stringify({
          chunk_size: chunkSize,
          chunk_overlap: chunkOverlap,
        });
      }
      await apiJson<Document>(`${basePath}/${id}/reindex`, options);
      setDocs((prev) =>
        prev.map((d) => (d.id === id ? { ...d, status: "pending", error_message: null } : d)),
      );
      onChanged?.();
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  }

  async function handleViewChunks(id: string) {
    setLoadingChunksId(id);
    setError("");
    try {
      const payload = await apiJson<DocumentChunksPayload>(`/api/v1/documents/${id}/chunks`);
      setInspectingChunks(payload);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoadingChunksId(null);
    }
  }

  function toggleDocumentSelection(documentId: string) {
    setSelectedDocumentIds((current) =>
      current.includes(documentId)
        ? current.filter((id) => id !== documentId)
        : [...current, documentId],
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-sm font-semibold text-content-primary">{title}</h3>
        <div className="flex-1" />

        <button
          type="button"
          onClick={() => setShowReindexConfig((prev) => !prev)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border-primary bg-surface-secondary px-2.5 py-1.5 text-xs text-content-secondary hover:text-content-primary"
        >
          <SlidersHorizontal className="h-3.5 w-3.5" />
          <span>Re-index Chunking ({chunkSize}/{chunkOverlap})</span>
        </button>

        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-content-tertiary" />
          <input
            type="text"
            placeholder="Search..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="rounded-lg border border-border-primary bg-surface-secondary py-1.5 pl-8 pr-3 text-xs text-content-primary placeholder:text-content-tertiary focus:border-accent-primary focus:outline-none"
          />
        </div>

        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-lg border border-border-primary bg-surface-secondary px-2.5 py-1.5 text-xs text-content-primary focus:border-accent-primary focus:outline-none"
        >
          <option value="">All Status</option>
          <option value="indexed">Indexed</option>
          <option value="processing">Processing</option>
          <option value="pending">Pending</option>
          <option value="failed">Failed</option>
        </select>

        {canStartChat && (
          <button
            type="button"
            onClick={() => onStartChat?.(selectedDocumentIds)}
            disabled={selectedDocumentIds.length === 0}
            className="inline-flex items-center gap-2 rounded-lg border border-accent-primary/20 bg-accent-primary/10 px-3 py-1.5 text-xs font-medium text-accent-primary transition hover:bg-accent-primary/15 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <MessageSquare className="h-3.5 w-3.5" />
            {selectedDocumentIds.length > 1 ? "Chat with selected docs" : "Chat with selected doc"}
          </button>
        )}
      </div>

      {showReindexConfig && (
        <div className="flex flex-wrap items-center gap-4 rounded-xl border border-border-primary bg-surface-secondary px-4 py-3 text-xs">
          <span className="font-medium text-content-primary">
            Chunking configuration for next Re-index:
          </span>
          <label className="flex items-center gap-2">
            <span className="text-content-secondary">Chunk size:</span>
            <input
              type="number"
              min={64}
              max={4096}
              value={chunkSize}
              onChange={(e) => setChunkSize(Math.max(64, Number(e.target.value) || 512))}
              className="w-24 rounded-lg border border-border-primary bg-surface-primary px-2 py-1 text-content-primary"
            />
          </label>
          <label className="flex items-center gap-2">
            <span className="text-content-secondary">Overlap:</span>
            <input
              type="number"
              min={0}
              max={1024}
              value={chunkOverlap}
              onChange={(e) => setChunkOverlap(Math.max(0, Number(e.target.value) || 0))}
              className="w-20 rounded-lg border border-border-primary bg-surface-primary px-2 py-1 text-content-primary"
            />
          </label>
        </div>
      )}

      {error && (
        <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          {error}
        </p>
      )}
      <div className="overflow-x-auto rounded-xl border border-border-primary">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border-primary bg-surface-secondary text-left text-xs font-medium uppercase tracking-wider text-content-tertiary">
              {canStartChat && <th className="px-4 py-3">Use</th>}
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Chunks</th>
              <th className="px-4 py-3">Size</th>
              <th className="px-4 py-3">Uploaded</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-primary">
            {docs.length === 0 ? (
              <tr>
                <td
                  colSpan={canStartChat ? 7 : 6}
                  className="px-4 py-12 text-center text-sm text-content-tertiary"
                >
                  No documents found
                </td>
              </tr>
            ) : (
              docs.map((doc) => (
                <tr key={doc.id} className="transition-colors hover:bg-surface-secondary">
                  {canStartChat && (
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selectedDocumentIds.includes(doc.id)}
                        disabled={doc.status !== "indexed"}
                        onChange={() => toggleDocumentSelection(doc.id)}
                        aria-label={`Use ${doc.file_name} in chat`}
                        className="h-4 w-4 rounded border-border-primary bg-surface-secondary text-accent-primary focus:ring-accent-primary disabled:opacity-40"
                      />
                    </td>
                  )}
                  <td className="px-4 py-3">
                    <div>
                      <p className="font-medium text-content-primary">{doc.title}</p>
                      <p className="text-xs text-content-tertiary">{doc.file_name}</p>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="space-y-1">
                      <StatusBadge status={doc.status} />
                      <p
                        className={`text-xs ${
                          doc.status === "failed" && doc.error_message
                            ? "text-red-400"
                            : "text-content-tertiary"
                        }`}
                      >
                        {getDocumentStatusDescription(doc.status, doc.error_message)}
                      </p>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-content-secondary">{doc.total_chunks}</td>
                  <td className="px-4 py-3 text-content-secondary">
                    {formatDocumentSize(doc.file_size)}
                  </td>
                  <td className="px-4 py-3 text-content-secondary">
                    {new Date(doc.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      {canStartChat && doc.status === "indexed" && (
                        <button
                          onClick={() => onStartChat?.([doc.id])}
                          className="rounded p-1 text-content-tertiary hover:bg-accent-primary/10 hover:text-accent-primary"
                          title="Chat with this document"
                        >
                          <MessageSquare className="h-3.5 w-3.5" />
                        </button>
                      )}
                      {doc.status === "indexed" && (
                        <button
                          onClick={() => void handleViewChunks(doc.id)}
                          disabled={loadingChunksId === doc.id}
                          className="rounded p-1 text-content-tertiary hover:bg-surface-tertiary hover:text-content-primary"
                          title="Inspect chunks and sections"
                          aria-label={`Inspect chunks of ${doc.file_name}`}
                        >
                          <Eye className="h-3.5 w-3.5" />
                        </button>
                      )}
                      <button
                        onClick={() => handleReindex(doc.id)}
                        className="rounded p-1 text-content-tertiary hover:bg-surface-tertiary hover:text-content-primary"
                        title="Re-index"
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => handleDelete(doc.id)}
                        className="rounded p-1 text-content-tertiary hover:bg-red-500/10 hover:text-red-400"
                        title="Delete"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {inspectingChunks && (
        <div className="rounded-xl border border-border-primary bg-surface-secondary p-4">
          <div className="flex items-center justify-between border-b border-border-primary pb-3">
            <div>
              <h4 className="text-sm font-semibold text-content-primary">
                Chunks Inspector: {inspectingChunks.title} ({inspectingChunks.total_chunks} chunks)
              </h4>
              <p className="text-xs text-content-tertiary">
                Chunk Size: {inspectingChunks.chunk_size} tokens · Overlap: {inspectingChunks.chunk_overlap} tokens ·{" "}
                Sections ({inspectingChunks.sections.length}): {inspectingChunks.sections.join(", ") || "Overview"}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setInspectingChunks(null)}
              className="rounded-lg p-1 text-content-tertiary hover:bg-surface-tertiary hover:text-content-primary"
              aria-label="Close chunk inspector"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="mt-3 max-h-80 space-y-2 overflow-y-auto pr-1">
            {inspectingChunks.chunks.map((c) => (
              <div
                key={c.id}
                className="rounded-lg border border-border-primary bg-surface-primary p-3 text-xs"
              >
                <div className="mb-1 flex flex-wrap items-center justify-between gap-2 text-content-tertiary">
                  <span className="font-semibold text-accent-primary">
                    Chunk #{c.chunk_index} · {c.section_path || c.section || "Overview"}
                  </span>
                  <span>
                    Page {c.page_number ?? 1} · {c.token_count} tokens · {c.block_type || "body"}
                  </span>
                </div>
                <p className="whitespace-pre-wrap text-content-secondary">{c.content}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-content-tertiary">
          <span>
            Page {page} of {totalPages} ({total} documents)
          </span>
          <div className="flex gap-1">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="rounded-lg border border-border-primary p-1.5 hover:bg-surface-secondary disabled:opacity-30"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="rounded-lg border border-border-primary p-1.5 hover:bg-surface-secondary disabled:opacity-30"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

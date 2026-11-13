export interface Document {
  id: string;
  title: string;
  file_name: string;
  file_type: string;
  file_size: number;
  status: string;
  total_chunks: number;
  error_message?: string | null;
  metadata_?: Record<string, any> | null;
  created_at: string;
}

export interface DocumentTableProps {
  mode?: "user" | "admin";
  title?: string;
  onChanged?: () => void;
  onStartChat?: (documentIds: string[]) => void;
}

export interface DocumentListResponse {
  items: Document[];
  total: number;
}

export function getDocumentBasePath(mode: "user" | "admin") {
  return mode === "admin" ? "/api/v1/admin/documents" : "/api/v1/documents";
}

export function formatDocumentSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function getDocumentStatusDescription(
  status: string,
  errorMessage?: string | null,
  metadata?: Record<string, any> | null,
) {
  if (status === "pending") return "Queued for indexing";
  if (status === "processing") {
    const stageMsg = metadata?.stage_message;
    if (typeof stageMsg === "string" && stageMsg.trim()) {
      return `Indexing in progress (${stageMsg})`;
    }
    return "Indexing in progress";
  }
  if (status === "indexed") return "Ready for chat retrieval";
  if (status === "failed") return errorMessage || "Re-index or upload again";
  return "Status unavailable";
}

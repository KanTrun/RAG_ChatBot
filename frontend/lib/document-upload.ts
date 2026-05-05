"use client";

import { apiJson } from "@/lib/client-api";

export type DocumentUploadStatus = "pending" | "processing" | "indexed" | "failed";

export interface UploadedDocument {
  id: string;
  title: string;
  file_name: string;
  file_type: string;
  file_size: number;
  status: DocumentUploadStatus;
  total_chunks: number;
  created_at: string;
  updated_at: string;
  duplicate_of_existing?: boolean;
  error_message?: string | null;
}

const TERMINAL_DOCUMENT_STATUSES = new Set<DocumentUploadStatus>(["indexed", "failed"]);

async function wait(delayMs: number) {
  await new Promise((resolve) => window.setTimeout(resolve, delayMs));
}

export async function pollUploadedDocumentStatus(
  documentId: string,
  onUpdate: (document: UploadedDocument) => void,
  intervalMs = 1500,
  maxAttempts = 20,
) {
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const document = await apiJson<UploadedDocument>(`/api/v1/documents/${documentId}`);
    onUpdate(document);

    if (TERMINAL_DOCUMENT_STATUSES.has(document.status)) {
      return document;
    }

    await wait(intervalMs);
  }

  return null;
}

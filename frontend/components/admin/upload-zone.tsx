"use client";

import { useCallback, useState } from "react";
import { Upload } from "lucide-react";
import { StatusBadge } from "@/components/shared/status-badge";
import { apiUpload, getApiErrorMessage } from "@/lib/client-api";
import {
  pollUploadedDocumentStatus,
  type UploadedDocument,
} from "@/lib/document-upload";

interface UploadFile {
  file: File;
  status: "uploading" | "pending" | "processing" | "indexed" | "failed";
  error?: string;
  duplicateOfExisting?: boolean;
}

interface UploadZoneProps {
  onUploadComplete: () => void;
  title?: string;
}

export function UploadZone({ onUploadComplete, title = "Upload Documents" }: UploadZoneProps) {
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [dragging, setDragging] = useState(false);

  const updateFile = useCallback(
    (
      file: File,
      update: Partial<Pick<UploadFile, "status" | "error" | "duplicateOfExisting">>,
    ) => {
      setFiles((prev) => prev.map((item) => (item.file === file ? { ...item, ...update } : item)));
    },
    [],
  );

  const uploadFile = useCallback(
    async (file: File) => {
      const entry: UploadFile = { file, status: "uploading" };
      setFiles((prev) => [...prev, entry]);

      try {
        const document = await apiUpload<UploadedDocument>("/api/v1/documents/upload", file);
        updateFile(file, {
          status: document.status,
          duplicateOfExisting: document.duplicate_of_existing,
          error: undefined,
        });
        onUploadComplete();

        if (document.status === "pending" || document.status === "processing") {
          const settledDocument = await pollUploadedDocumentStatus(document.id, (nextDocument) => {
            updateFile(file, {
              status: nextDocument.status,
              duplicateOfExisting: nextDocument.duplicate_of_existing,
              error: nextDocument.error_message || undefined,
            });
          });

          if (settledDocument) {
            onUploadComplete();
          }
        }
      } catch (error) {
        updateFile(file, { status: "failed", error: getApiErrorMessage(error) });
      }
    },
    [onUploadComplete, updateFile],
  );

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const dropped = Array.from(e.dataTransfer.files);
    dropped.forEach(uploadFile);
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(e.target.files || []);
    selected.forEach(uploadFile);
    e.target.value = "";
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-content-primary">{title}</h3>

      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 transition-colors ${
          dragging
            ? "border-accent-primary bg-accent-primary/5"
            : "border-border-primary hover:border-content-tertiary"
        }`}
      >
        <Upload className="mb-2 h-8 w-8 text-content-tertiary" />
        <p className="text-sm text-content-secondary">
          Drag files here or click to browse
        </p>
        <p className="mt-1 text-xs text-content-tertiary">
          PDF, DOCX, TXT, MD, HTML — Max 50MB
        </p>
        <input
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.md,.html"
          onChange={handleFileSelect}
          className="hidden"
        />
      </label>

      {/* File progress list */}
      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((f, i) => (
            <li
              key={i}
              className="flex items-center gap-3 rounded-lg border border-border-primary bg-surface-primary px-3 py-2"
            >
              <span className="min-w-0 flex-1 truncate text-xs text-content-primary">
                {f.file.name}
                {f.duplicateOfExisting ? " (already uploaded)" : ""}
              </span>
              <StatusBadge
                status={
                  f.status === "failed"
                    ? "failed"
                    : f.status === "uploading"
                      ? "processing"
                      : f.status
                }
              />
              {f.status === "uploading" && (
                <span className="text-xs text-content-tertiary">Uploading</span>
              )}
              {f.error && (
                <span className="max-w-36 truncate text-xs text-red-400" title={f.error}>
                  {f.error}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

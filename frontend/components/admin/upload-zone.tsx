"use client";

import { useCallback, useState } from "react";
import { SlidersHorizontal, Upload } from "lucide-react";
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
  const [chunkSize, setChunkSize] = useState(512);
  const [chunkOverlap, setChunkOverlap] = useState(51);
  const [showChunkConfig, setShowChunkConfig] = useState(false);

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
        const extraFields = showChunkConfig
          ? { chunk_size: chunkSize, chunk_overlap: chunkOverlap }
          : undefined;
        const document = await apiUpload<UploadedDocument>(
          "/api/v1/documents/upload",
          file,
          extraFields,
        );
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
    [chunkOverlap, chunkSize, onUploadComplete, showChunkConfig, updateFile],
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
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-content-primary">{title}</h3>
        <button
          type="button"
          onClick={() => setShowChunkConfig((prev) => !prev)}
          className="inline-flex items-center gap-1 rounded-lg border border-border-primary bg-surface-secondary px-2.5 py-1 text-xs text-content-secondary hover:text-content-primary"
        >
          <SlidersHorizontal className="h-3 w-3" />
          <span>Chunk Config ({chunkSize}/{chunkOverlap})</span>
        </button>
      </div>

      {showChunkConfig && (
        <div className="grid grid-cols-2 gap-3 rounded-xl border border-border-primary bg-surface-secondary p-3 text-xs">
          <label className="space-y-1">
            <span className="block text-content-secondary">Chunk size (tokens)</span>
            <input
              type="number"
              min={64}
              max={4096}
              value={chunkSize}
              onChange={(e) => setChunkSize(Math.max(64, Number(e.target.value) || 512))}
              className="w-full rounded-lg border border-border-primary bg-surface-primary px-2.5 py-1.5 text-content-primary"
            />
          </label>
          <label className="space-y-1">
            <span className="block text-content-secondary">Overlap (tokens)</span>
            <input
              type="number"
              min={0}
              max={1024}
              value={chunkOverlap}
              onChange={(e) => setChunkOverlap(Math.max(0, Number(e.target.value) || 0))}
              className="w-full rounded-lg border border-border-primary bg-surface-primary px-2.5 py-1.5 text-content-primary"
            />
          </label>
        </div>
      )}

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

      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((f, i) => (
            <li
              key={i}
              className="flex flex-col gap-1 rounded-lg border border-border-primary bg-surface-primary px-3 py-2"
            >
              <div className="flex items-center gap-3">
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
              </div>
              {f.error && (
                <p className="text-xs text-red-400" title={f.error}>
                  Error: {f.error}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

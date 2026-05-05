"use client";

import { FileText, Layers3, X } from "lucide-react";

export interface ActiveDocument {
  id: string;
  title: string;
  file_name: string;
  status: string;
  total_chunks: number;
}

interface ActiveDocumentContextBarProps {
  documents: ActiveDocument[];
  disabled?: boolean;
  onRemove: (documentId: string) => void;
  onClear: () => void;
}

function getStatusTone(status: string) {
  if (status === "indexed") return "border-emerald-400/20 bg-emerald-400/10 text-emerald-200";
  if (status === "processing" || status === "pending") {
    return "border-amber-400/20 bg-amber-400/10 text-amber-100";
  }
  return "border-red-400/20 bg-red-400/10 text-red-200";
}

export function ActiveDocumentContextBar({
  documents,
  disabled,
  onRemove,
  onClear,
}: ActiveDocumentContextBarProps) {
  if (documents.length === 0) {
    return null;
  }

  return (
    <div className="border-t border-border-primary bg-surface-primary/80 px-4 py-3 backdrop-blur-sm">
      <div className="mx-auto flex max-w-3xl flex-col gap-3 rounded-[24px] border border-white/8 bg-white/[0.03] px-4 py-3 shadow-[0_18px_48px_rgba(2,6,23,0.22)]">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-2 rounded-full border border-accent-primary/20 bg-accent-primary/10 px-3 py-1 text-xs font-medium text-accent-primary">
            <Layers3 className="h-3.5 w-3.5" />
            {documents.length === 1 ? "Using 1 active document" : `Using ${documents.length} active documents`}
          </span>
          <p className="text-xs text-content-tertiary">
            Retrieval will prioritize only these selected documents for this conversation.
          </p>
          <button
            type="button"
            onClick={onClear}
            disabled={disabled}
            className="ml-auto rounded-full border border-white/10 px-2.5 py-1 text-[11px] font-medium text-content-secondary transition hover:border-white/20 hover:bg-white/[0.05] hover:text-content-primary disabled:opacity-50"
          >
            Clear all
          </button>
        </div>

        <div className="flex flex-wrap gap-2">
          {documents.map((document) => (
            <div
              key={document.id}
              className={`group flex items-center gap-2 rounded-2xl border px-3 py-2 text-xs shadow-[0_12px_24px_rgba(2,6,23,0.16)] ${getStatusTone(document.status)}`}
            >
              <FileText className="h-3.5 w-3.5 shrink-0" />
              <div className="min-w-0">
                <p className="truncate font-medium">{document.title}</p>
                <p className="truncate text-[11px] opacity-80">
                  {document.file_name} · {document.total_chunks} chunks
                </p>
              </div>
              <button
                type="button"
                onClick={() => onRemove(document.id)}
                disabled={disabled}
                className="rounded-full p-1 opacity-70 transition hover:bg-black/10 hover:opacity-100 disabled:opacity-40"
                aria-label={`Remove ${document.file_name} from active documents`}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

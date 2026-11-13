"use client";

import { useState } from "react";
import { ChevronDown, FileText, Layers3, X } from "lucide-react";

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

const MAX_INLINE_CHIPS = 2;

function getStatusTone(status: string) {
  if (status === "indexed") return "border-emerald-500/25 bg-emerald-500/10 text-emerald-300";
  if (status === "processing" || status === "pending") {
    return "border-amber-500/25 bg-amber-500/10 text-amber-200";
  }
  return "border-red-500/25 bg-red-500/10 text-red-300";
}

export function ActiveDocumentContextBar({
  documents,
  disabled,
  onRemove,
  onClear,
}: ActiveDocumentContextBarProps) {
  const [popoverOpen, setPopoverOpen] = useState(false);

  if (documents.length === 0) {
    return null;
  }

  const visibleDocs = documents.slice(0, MAX_INLINE_CHIPS);
  const hiddenDocs = documents.slice(MAX_INLINE_CHIPS);

  return (
    <div className="relative shrink-0 border-t border-border-primary bg-surface-primary/90 px-4 py-2 backdrop-blur-sm">
      <div className="mx-auto flex max-w-3xl flex-wrap items-center gap-2 rounded-2xl border border-border-primary bg-surface-secondary/75 px-3 py-2">
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-accent-primary/25 bg-accent-primary/10 px-2.5 py-0.5 text-xs font-medium text-accent-primary">
          <Layers3 className="h-3.5 w-3.5" />
          {documents.length === 1
            ? "Using 1 active document"
            : `Using ${documents.length} active documents`}
        </span>

        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
          {visibleDocs.map((document) => (
            <div
              key={document.id}
              className={`inline-flex max-w-[220px] items-center gap-1.5 rounded-xl border px-2.5 py-1 text-xs ${getStatusTone(
                document.status,
              )}`}
              title={`${document.title} (${document.file_name} · ${document.total_chunks} chunks)`}
            >
              <FileText className="h-3 w-3 shrink-0" />
              <span className="truncate font-medium">{document.title}</span>
              <button
                type="button"
                onClick={() => onRemove(document.id)}
                disabled={disabled}
                className="rounded-full p-0.5 opacity-75 transition hover:bg-black/15 hover:opacity-100 disabled:opacity-40"
                aria-label={`Remove ${document.file_name} from active documents`}
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}

          {hiddenDocs.length > 0 && (
            <div className="relative">
              <button
                type="button"
                onClick={() => setPopoverOpen((prev) => !prev)}
                className="inline-flex items-center gap-1 rounded-xl border border-border-primary bg-surface-tertiary px-2.5 py-1 text-xs font-medium text-content-secondary transition hover:text-content-primary"
                aria-expanded={popoverOpen}
              >
                <span>+{hiddenDocs.length} more</span>
                <ChevronDown className="h-3 w-3" />
              </button>

              {popoverOpen && (
                <div className="absolute bottom-[calc(100%+0.5rem)] left-0 z-40 max-h-56 w-72 overflow-y-auto rounded-2xl border border-border-primary bg-surface-secondary p-2 shadow-2xl animate-scale-pop">
                  <div className="mb-1.5 flex items-center justify-between px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-content-tertiary">
                    <span>Selected Documents ({documents.length})</span>
                    <button
                      type="button"
                      onClick={() => setPopoverOpen(false)}
                      className="rounded p-0.5 hover:bg-surface-tertiary hover:text-content-primary"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                  <div className="space-y-1">
                    {documents.map((doc) => (
                      <div
                        key={doc.id}
                        className="flex items-center justify-between gap-2 rounded-xl border border-border-primary/60 bg-surface-primary px-2.5 py-1.5 text-xs"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-medium text-content-primary">{doc.title}</p>
                          <p className="truncate text-[11px] text-content-tertiary">
                            {doc.file_name} · {doc.total_chunks} chunks
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => onRemove(doc.id)}
                          disabled={disabled}
                          className="rounded-lg p-1 text-content-tertiary hover:bg-red-500/10 hover:text-red-400 disabled:opacity-40"
                          aria-label={`Remove ${doc.file_name} from active documents`}
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={onClear}
          disabled={disabled}
          className="ml-auto shrink-0 rounded-full border border-border-primary px-2.5 py-1 text-[11px] font-medium text-content-secondary transition hover:bg-surface-tertiary hover:text-content-primary disabled:opacity-50"
        >
          Clear all
        </button>
      </div>
    </div>
  );
}

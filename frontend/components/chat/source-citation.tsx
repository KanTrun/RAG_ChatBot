"use client";

import { useState } from "react";

interface CitationSourcePreview {
  citation_number?: number;
  document_title?: string;
  file_name?: string;
  section?: string | null;
  section_path?: string | null;
  page_number?: number | null;
  score?: number;
  excerpt?: string | null;
}

interface SourceCitationProps {
  number: number;
  onClick: (num: number, sources?: unknown[]) => void;
  sources?: unknown[];
}

export function SourceCitation({ number, onClick, sources }: SourceCitationProps) {
  const [hovered, setHovered] = useState(false);

  const matchedSource = Array.isArray(sources)
    ? (sources.find(
        (item: any) => Number(item?.citation_number) === number,
      ) as CitationSourcePreview | undefined)
    : undefined;

  return (
    <span
      className="relative inline-block align-baseline"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        type="button"
        onFocus={() => setHovered(true)}
        onBlur={() => setHovered(false)}
        onClick={() => {
          if (sources) {
            onClick(number, sources);
            return;
          }
          onClick(number);
        }}
        className="mx-0.5 inline-flex items-center rounded-md bg-teal-500/20 px-1.5 py-0.5 text-xs font-semibold text-teal-400 transition-colors hover:bg-teal-500/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/50"
        aria-label={`Source ${number}`}
      >
        {number}
      </button>

      {hovered && matchedSource && (
        <span
          role="tooltip"
          className="pointer-events-none absolute bottom-[calc(100%+6px)] left-1/2 z-40 w-64 -translate-x-1/2 rounded-xl border border-border-primary bg-surface-secondary p-2.5 text-left shadow-xl animate-scale-pop"
        >
          <span className="flex items-center justify-between gap-2 text-[11px] font-semibold text-content-primary">
            <span className="truncate">
              [{number}] {matchedSource.document_title || matchedSource.file_name}
            </span>
            {typeof matchedSource.score === "number" && (
              <span className="shrink-0 rounded bg-teal-500/15 px-1.5 py-0.5 font-mono text-[10px] text-teal-400">
                {matchedSource.score.toFixed(2)}
              </span>
            )}
          </span>
          {(matchedSource.section_path || matchedSource.section) && (
            <span className="mt-0.5 block truncate text-[10px] text-content-tertiary">
              {matchedSource.section_path || matchedSource.section}
            </span>
          )}
          {matchedSource.excerpt && (
            <span className="mt-1 line-clamp-3 block text-[11px] leading-4 text-content-secondary">
              {matchedSource.excerpt}
            </span>
          )}
        </span>
      )}
    </span>
  );
}

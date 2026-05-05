"use client";

import { FileText, X } from "lucide-react";

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
}

interface SourcesPanelProps {
  sources: Source[];
  activeCitation: number | null;
  onClose: () => void;
}

function humanizeAnswerSection(value: string | null | undefined) {
  if (!value) return "General evidence";
  return value.replaceAll("_", " ");
}

function groupSources(sources: Source[]) {
  const grouped = new Map<string, Source[]>();
  for (const source of sources) {
    const key = humanizeAnswerSection(source.answer_section);
    const bucket = grouped.get(key) ?? [];
    bucket.push(source);
    grouped.set(key, bucket);
  }
  return Array.from(grouped.entries());
}

export function SourcesPanel({ sources, activeCitation, onClose }: SourcesPanelProps) {
  const groupedSources = groupSources(sources);

  return (
    <aside className="flex h-full min-h-0 w-80 shrink-0 flex-col border-l border-border-primary bg-surface-secondary">
      <div className="flex items-center justify-between border-b border-border-primary px-4 py-3">
        <h3 className="text-sm font-semibold text-content-primary">Sources</h3>
        <button
          onClick={onClose}
          className="rounded-lg p-1 text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
          aria-label="Close sources panel"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {sources.length === 0 ? (
          <p className="py-8 text-center text-xs text-content-tertiary">
            No sources for this response
          </p>
        ) : (
          <div className="space-y-4">
            {groupedSources.map(([group, items]) => (
              <section key={group} className="space-y-2">
                <div className="sticky top-0 z-10 rounded-lg border border-border-primary bg-surface-secondary/95 px-3 py-2 backdrop-blur">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-content-tertiary">
                    {group}
                  </p>
                  <p className="mt-1 text-xs text-content-secondary">
                    {items.length} source{items.length > 1 ? "s" : ""}
                  </p>
                </div>
                <ul className="space-y-2">
                  {items.map((src) => (
                    <li
                      key={src.citation_number}
                      className={`rounded-lg border p-3 transition-colors ${
                        activeCitation === src.citation_number
                          ? "border-teal-500/50 bg-teal-500/5"
                          : "border-border-primary bg-surface-primary"
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-teal-500/20 text-xs font-bold text-teal-400">
                          {src.citation_number}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-content-primary">
                            {src.document_title}
                          </p>
                          <div className="mt-1 flex items-center gap-2 text-xs text-content-tertiary">
                            <FileText className="h-3 w-3" />
                            <span className="truncate">{src.file_name}</span>
                            {(src.page_start ?? src.page_number) && (
                              <span>
                                p.
                                {src.page_start ?? src.page_number}
                                {src.page_end && src.page_end !== src.page_start ? `-${src.page_end}` : ""}
                              </span>
                            )}
                          </div>
                          {(src.section_path || src.section) && (
                            <p className="mt-1 truncate text-xs text-content-secondary">
                              {src.section_path || src.section}
                            </p>
                          )}
                          <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                            {src.block_type && (
                              <span className="rounded-full border border-border-primary px-2 py-0.5 text-content-tertiary">
                                {src.block_type.replaceAll("_", " ")}
                              </span>
                            )}
                            {src.answer_section && (
                              <span className="rounded-full border border-teal-500/30 bg-teal-500/10 px-2 py-0.5 text-teal-300">
                                {src.answer_section.replaceAll("_", " ")}
                              </span>
                            )}
                            {src.heading_level && (
                              <span className="rounded-full border border-border-primary px-2 py-0.5 text-content-tertiary">
                                H{src.heading_level}
                              </span>
                            )}
                          </div>
                          {src.excerpt && (
                            <div className="mt-2 rounded-lg border border-border-primary/70 bg-surface-secondary px-2.5 py-2">
                              <p className="mb-1 text-[11px] font-medium uppercase tracking-[0.08em] text-content-tertiary">
                                Evidence snippet
                              </p>
                              <p className="text-xs leading-5 text-content-secondary">
                                {src.excerpt}
                              </p>
                            </div>
                          )}
                          <p className="mt-2 text-[11px] text-content-tertiary">
                            Evidence score {src.score.toFixed(2)}
                          </p>
                          {src.selection_reason && (
                            <p className="mt-1 text-[11px] text-content-tertiary">
                              {src.selection_reason}
                            </p>
                          )}
                          {src.ingestion_version && (
                            <p className="mt-1 text-[11px] text-content-tertiary">
                              Indexed with {src.ingestion_version}
                            </p>
                          )}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}

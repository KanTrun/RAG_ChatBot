"use client";

interface SourceCitationProps {
  number: number;
  onClick: (num: number, sources?: unknown[]) => void;
  sources?: unknown[];
}

export function SourceCitation({ number, onClick, sources }: SourceCitationProps) {
  return (
    <button
      onClick={() => {
        if (sources) {
          onClick(number, sources);
          return;
        }
        onClick(number);
      }}
      className="mx-0.5 inline-flex items-center rounded-md bg-teal-500/20 px-1.5 py-0.5 text-xs font-semibold text-teal-400 transition-colors hover:bg-teal-500/30"
      aria-label={`Source ${number}`}
    >
      {number}
    </button>
  );
}

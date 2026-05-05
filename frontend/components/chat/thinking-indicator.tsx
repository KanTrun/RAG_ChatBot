"use client";

import { useEffect, useState } from "react";

const PHRASES = [
  "Analyzing your question",
  "Checking your documents",
  "Drafting a clear answer",
];

interface ThinkingIndicatorProps {
  compact?: boolean;
}

export function ThinkingIndicator({ compact = false }: ThinkingIndicatorProps) {
  const [phraseIndex, setPhraseIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setPhraseIndex((current) => (current + 1) % PHRASES.length);
    }, 1400);
    return () => window.clearInterval(timer);
  }, []);

  const content = (
    <div
      className={`relative overflow-hidden rounded-[22px] border border-white/8 bg-white/[0.04] shadow-[0_18px_48px_rgba(2,6,23,0.28)] ${
        compact ? "px-4 py-3" : "px-4 py-3.5"
      }`}
    >
      <div className="pointer-events-none absolute inset-0 chat-skeleton-shimmer opacity-70" />
      <div className="relative flex items-center gap-3">
        <div className="flex gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-accent-primary chat-live-dot [animation-delay:0ms]" />
          <span className="h-2.5 w-2.5 rounded-full bg-accent-secondary chat-live-dot [animation-delay:160ms]" />
          <span className="h-2.5 w-2.5 rounded-full bg-accent-citation chat-live-dot [animation-delay:320ms]" />
        </div>
        <div className="space-y-1">
          <p className="text-sm font-medium text-content-primary">{PHRASES[phraseIndex]}</p>
          <p className="text-xs text-content-tertiary">Streaming response as soon as it is ready</p>
        </div>
      </div>
    </div>
  );

  if (compact) {
    return <div aria-busy="true">{content}</div>;
  }

  return (
    <div className="flex justify-start px-4 pb-4" aria-busy="true">
      <div className="mx-auto flex max-w-3xl items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-accent-primary/20 bg-accent-primary/12 text-accent-primary shadow-[0_12px_30px_rgba(99,102,241,0.2)]">
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="12" cy="12" r="3" />
          </svg>
        </div>
        {content}
      </div>
    </div>
  );
}

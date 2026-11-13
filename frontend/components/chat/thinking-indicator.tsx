"use client";

import { useEffect, useState } from "react";

const PHRASES = [
  "Đang phân tích câu hỏi...",
  "Đang tìm tài liệu liên quan...",
  "Đang tổng hợp câu trả lời bám nguồn...",
];

interface ThinkingIndicatorProps {
  compact?: boolean;
  loadingModel?: boolean;
  stage?: "retrieving" | "generating" | "loading_model" | string;
  statusText?: string;
}

export function ThinkingIndicator({
  compact = false,
  loadingModel = false,
  stage,
  statusText,
}: ThinkingIndicatorProps) {
  const [phraseIndex, setPhraseIndex] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setPhraseIndex((current) => (current + 1) % PHRASES.length);
    }, 1600);
    const elapsedTimer = window.setInterval(() => {
      setElapsedSeconds((sec) => sec + 1);
    }, 1000);
    return () => {
      window.clearInterval(timer);
      window.clearInterval(elapsedTimer);
    };
  }, []);

  const showModelWarmupNotice = loadingModel || stage === "loading_model" || elapsedSeconds >= 6;

  let primaryLabel = statusText || PHRASES[phraseIndex];
  if (showModelWarmupNotice && !statusText) {
    primaryLabel = "Đang tải model, vui lòng chờ...";
  } else if (stage === "retrieving" && !statusText) {
    primaryLabel = "Đang tìm tài liệu...";
  } else if (stage === "generating" && !statusText) {
    primaryLabel = "Đang tổng hợp câu trả lời...";
  }

  const content = (
    <div
      className={`relative overflow-hidden rounded-[22px] border border-border-primary bg-surface-secondary/70 shadow-sm ${
        compact ? "px-4 py-2.5" : "px-4 py-3"
      }`}
    >
      <div className="pointer-events-none absolute inset-0 chat-skeleton-shimmer opacity-60" />
      <div className="relative flex items-center gap-3">
        <div className="flex gap-1.5">
          <span className="h-2 w-2 rounded-full bg-accent-primary chat-live-dot [animation-delay:0ms]" />
          <span className="h-2 w-2 rounded-full bg-accent-secondary chat-live-dot [animation-delay:160ms]" />
          <span className="h-2 w-2 rounded-full bg-accent-citation chat-live-dot [animation-delay:320ms]" />
        </div>
        <div className="min-w-0 flex-1 space-y-0.5">
          <div className="flex items-center justify-between gap-3">
            <p className="truncate text-sm font-medium text-content-primary">
              {primaryLabel}
            </p>
            <span className="shrink-0 font-mono text-[11px] text-content-tertiary">
              {elapsedSeconds}s
            </span>
          </div>
          <p className="text-xs text-content-tertiary">
            {showModelWarmupNotice
              ? "Model LLM đang khởi tạo trên CPU (tối đa 120 giây cho lần gọi đầu tiên)"
              : "Phản hồi trực tiếp theo từng token ngay khi sẵn sàng"}
          </p>
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
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl border border-accent-primary/20 bg-accent-primary/12 text-accent-primary">
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="12" cy="12" r="3" />
          </svg>
        </div>
        {content}
      </div>
    </div>
  );
}

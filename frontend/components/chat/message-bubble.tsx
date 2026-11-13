"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Activity,
  Bot,
  Check,
  Copy,
  Globe,
  PencilLine,
  RefreshCcw,
  Trash2,
  User,
} from "lucide-react";
import { OverflowActionMenu } from "./overflow-action-menu";
import { SourceCitation } from "./source-citation";
import { ThinkingIndicator } from "./thinking-indicator";

export interface RetrievalDiagnostics {
  intent?: string;
  candidate_count?: number;
  vector_candidates_count?: number;
  bm25_candidates_count?: number;
  bm25_used?: boolean;
  bm25_contributed?: boolean;
  top_k_scores?: number[];
  latency_breakdown_ms?: {
    rewrite_ms?: number;
    retrieval_ms?: number;
    rerank_ms?: number;
    generation_ms?: number;
    total_ms?: number;
  };
  tokens?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
  abstained?: boolean;
  used_outside_knowledge?: boolean;
  low_support_reason?: string | null;
  invalid_citations_removed?: number[];
}

interface MessageBubbleProps {
  message: {
    id: string;
    role: "user" | "assistant";
    content: string;
    sources?: any[];
    state?: "streaming" | "complete" | "error";
    loadingModel?: boolean;
    streamStage?: string;
    streamStatusText?: string;
    usedOutsideKnowledge?: boolean;
    abstained?: boolean;
    diagnostics?: RetrievalDiagnostics | null;
    latency_ms?: number | null;
    tokens_used?: number | null;
  };
  onCitationClick: (num: number, sources?: any[]) => void;
  onDelete?: (messageId: string) => void;
  onEditAndResend?: (messageId: string, content: string) => void;
  onRegenerate?: (messageId: string) => void;
  onCopy?: (content: string) => void;
  deleteDisabled?: boolean;
}

function CodeBlockPre({ children, ...props }: React.HTMLAttributes<HTMLPreElement>) {
  const [copied, setCopied] = useState(false);

  function extractText(node: React.ReactNode): string {
    if (typeof node === "string" || typeof node === "number") return String(node);
    if (Array.isArray(node)) return node.map(extractText).join("");
    if (node && typeof node === "object" && "props" in node) {
      return extractText((node as any).props?.children);
    }
    return "";
  }

  async function handleCopyCode() {
    const codeText = extractText(children).replace(/\n$/, "");
    if (!codeText) return;
    try {
      await navigator.clipboard?.writeText(codeText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // ignore clipboard errors
    }
  }

  return (
    <div className="group relative my-2">
      <button
        type="button"
        onClick={() => void handleCopyCode()}
        className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-md border border-border-primary bg-surface-primary/90 px-2 py-1 text-[11px] font-medium text-content-secondary opacity-0 transition-opacity group-hover:opacity-100 hover:text-content-primary focus:opacity-100"
        aria-label="Copy code block"
      >
        {copied ? (
          <>
            <Check className="h-3 w-3 text-emerald-400" />
            <span>Copied</span>
          </>
        ) : (
          <>
            <Copy className="h-3 w-3" />
            <span>Copy</span>
          </>
        )}
      </button>
      <pre
        className="overflow-x-auto rounded-xl border border-border-primary bg-surface-secondary p-3 font-mono text-xs"
        {...props}
      >
        {children}
      </pre>
    </div>
  );
}

export function MessageBubble({
  message,
  onCitationClick,
  onDelete,
  onEditAndResend,
  onRegenerate,
  onCopy,
  deleteDisabled = false,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isStreaming = message.state === "streaming";
  const isError = message.state === "error";
  const showActions = !isStreaming;
  const diag = message.diagnostics;
  const usedOutside = Boolean(
    message.usedOutsideKnowledge || diag?.used_outside_knowledge,
  );
  const actionItems = isUser
    ? [
        {
          label: "Sửa và gửi lại",
          icon: PencilLine,
          disabled: deleteDisabled,
          onSelect: () => onEditAndResend?.(message.id, message.content),
        },
        {
          label: "Xóa đoạn chat",
          icon: Trash2,
          destructive: true,
          disabled: deleteDisabled,
          onSelect: () => onDelete?.(message.id),
        },
      ]
    : [
        {
          label: "Tạo lại câu trả lời",
          icon: RefreshCcw,
          disabled: deleteDisabled,
          onSelect: () => onRegenerate?.(message.id),
        },
        {
          label: "Sao chép",
          icon: Copy,
          disabled: !message.content.trim(),
          onSelect: () => onCopy?.(message.content),
        },
        {
          label: "Xóa đoạn chat",
          icon: Trash2,
          destructive: true,
          disabled: deleteDisabled,
          onSelect: () => onDelete?.(message.id),
        },
      ];

  return (
    <div className={`flex gap-3 animate-fade-slide-up ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-primary/20 text-accent-primary">
          <Bot className="h-4 w-4" />
        </div>
      )}

      <div
        className={`max-w-[85%] rounded-[24px] px-4 py-3 shadow-[0_18px_48px_rgba(2,6,23,0.18)] transition-all duration-200 ${
          isUser
            ? "rounded-br-md bg-linear-to-br from-accent-primary via-accent-secondary to-accent-primary-hover text-white"
            : isError
              ? "rounded-bl-md border border-red-500/30 bg-red-500/10 text-content-primary"
              : "rounded-bl-md border border-border-primary bg-surface-secondary/80 text-content-primary backdrop-blur-sm"
        }`}
      >
        {showActions && (
          <div className={`mb-2 flex ${isUser ? "justify-start" : "justify-end"}`}>
            <OverflowActionMenu
              buttonLabel={isUser ? "Mở menu tin nhắn người dùng" : "Mở menu tin nhắn trợ lý"}
              items={actionItems}
              align={isUser ? "left" : "right"}
              disabled={deleteDisabled}
            />
          </div>
        )}
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        ) : isStreaming && !message.content ? (
          <ThinkingIndicator
            compact
            loadingModel={message.loadingModel}
            stage={message.streamStage}
            statusText={message.streamStatusText}
          />
        ) : (
          <div className="prose prose-sm prose-invert max-w-none text-content-primary">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children, ...props }) => (
                  <p {...props}>
                    {processCitations(children, onCitationClick, message.sources)}
                  </p>
                ),
                li: ({ children, ...props }) => (
                  <li {...props}>
                    {processCitations(children, onCitationClick, message.sources)}
                  </li>
                ),
                td: ({ children, ...props }) => (
                  <td className="border border-border-primary px-2.5 py-1.5 text-xs" {...props}>
                    {processCitations(children, onCitationClick, message.sources)}
                  </td>
                ),
                th: ({ children, ...props }) => (
                  <th className="border border-border-primary bg-surface-tertiary px-2.5 py-1.5 text-left text-xs font-semibold" {...props}>
                    {children}
                  </th>
                ),
                h1: ({ children, ...props }) => (
                  <h1 {...props}>
                    {processCitations(children, onCitationClick, message.sources)}
                  </h1>
                ),
                h2: ({ children, ...props }) => (
                  <h2 {...props}>
                    {processCitations(children, onCitationClick, message.sources)}
                  </h2>
                ),
                h3: ({ children, ...props }) => (
                  <h3 {...props}>
                    {processCitations(children, onCitationClick, message.sources)}
                  </h3>
                ),
                code: ({ children, className, ...props }) => {
                  const isInline = !className;
                  return isInline ? (
                    <code className="rounded bg-surface-tertiary px-1.5 py-0.5 font-mono text-xs" {...props}>
                      {children}
                    </code>
                  ) : (
                    <code className={`${className} font-mono text-xs`} {...props}>
                      {children}
                    </code>
                  );
                },
                pre: ({ children, ...props }) => <CodeBlockPre {...props}>{children}</CodeBlockPre>,
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border-primary pt-2.5 text-[11px] text-content-tertiary">
            <button
              type="button"
              onClick={() => onCitationClick(message.sources?.[0]?.citation_number ?? 1, message.sources)}
              className="inline-flex h-5 items-center rounded-full border border-accent-citation/30 bg-accent-citation/10 px-2.5 font-medium text-accent-citation transition hover:bg-accent-citation/20"
            >
              {message.sources.length} source{message.sources.length > 1 ? "s" : ""}
            </button>
            <span>Grounded answer</span>
          </div>
        )}

        {!isUser && usedOutside && (
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-amber-500/20 pt-3 text-[11px] text-amber-300">
            <span className="inline-flex h-5 items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 font-medium text-amber-300">
              <Globe className="h-3 w-3" />
              Outside knowledge used (Ngoài tài liệu)
            </span>
            <span className="text-content-tertiary">
              Answered using general model knowledge because document evidence was insufficient.
            </span>
          </div>
        )}

        {!isUser && !isStreaming && diag && (
          <details className="mt-3 rounded-xl border border-border-primary/70 bg-surface-primary/60 px-3 py-2 text-xs text-content-secondary">
            <summary className="flex cursor-pointer items-center justify-between gap-2 font-medium text-content-tertiary hover:text-content-primary">
              <span className="inline-flex items-center gap-1.5">
                <Activity className="h-3.5 w-3.5 text-accent-primary" />
                <span>Chi tiết kỹ thuật (Retrieval & Latency Diagnostics)</span>
              </span>
              <span className="text-[11px]">
                {diag.intent ? `Intent: ${diag.intent}` : ""}
                {diag.latency_breakdown_ms?.total_ms !== undefined
                  ? ` · ${diag.latency_breakdown_ms.total_ms} ms`
                  : message.latency_ms
                    ? ` · ${message.latency_ms} ms`
                    : ""}
                {diag.tokens?.total_tokens !== undefined
                  ? ` · ${diag.tokens.total_tokens} tokens`
                  : message.tokens_used
                    ? ` · ${message.tokens_used} tokens`
                    : ""}
              </span>
            </summary>
            <div className="mt-2 grid gap-2 border-t border-border-primary/60 pt-2 text-[11px] sm:grid-cols-2">
              <div>
                <p className="font-semibold text-content-primary">Retrieval</p>
                <p>Intent: <span className="font-mono text-content-primary">{diag.intent || "question"}</span></p>
                <p>
                  Candidates: <span className="font-mono text-content-primary">{diag.candidate_count ?? 0}</span>{" "}
                  (Vector: {diag.vector_candidates_count ?? 0}, BM25: {diag.bm25_candidates_count ?? 0})
                </p>
                <p>
                  BM25:{" "}
                  <span className="font-mono text-content-primary">
                    {diag.bm25_used
                      ? diag.bm25_contributed
                        ? "Enabled (Matched)"
                        : "Enabled (0 hits)"
                      : "Disabled"}
                  </span>
                </p>
                <p>
                  Top-k Scores:{" "}
                  <span className="font-mono text-content-primary">
                    {diag.top_k_scores && diag.top_k_scores.length > 0
                      ? diag.top_k_scores.map((s) => Number(s).toFixed(3)).join(", ")
                      : "N/A"}
                  </span>
                </p>
              </div>
              <div>
                <p className="font-semibold text-content-primary">Latency & Tokens</p>
                {diag.latency_breakdown_ms && (
                  <>
                    <p>
                      Rewrite: <span className="font-mono">{diag.latency_breakdown_ms.rewrite_ms ?? 0} ms</span> ·{" "}
                      Retrieval: <span className="font-mono">{diag.latency_breakdown_ms.retrieval_ms ?? 0} ms</span>
                    </p>
                    <p>
                      Rerank: <span className="font-mono">{diag.latency_breakdown_ms.rerank_ms ?? 0} ms</span> ·{" "}
                      Generation: <span className="font-mono">{diag.latency_breakdown_ms.generation_ms ?? 0} ms</span>
                    </p>
                    <p>
                      Total Latency: <span className="font-mono text-content-primary">{diag.latency_breakdown_ms.total_ms ?? 0} ms</span>
                    </p>
                  </>
                )}
                {diag.tokens && (
                  <p>
                    Tokens: <span className="font-mono text-content-primary">{diag.tokens.total_tokens ?? 0}</span>{" "}
                    (Prompt: {diag.tokens.prompt_tokens ?? 0}, Output: {diag.tokens.completion_tokens ?? 0})
                  </p>
                )}
              </div>
            </div>
          </details>
        )}

        {!isUser && isStreaming && message.content && (
          <div className="mt-3 flex items-center gap-2 text-[11px] text-content-tertiary">
            <span className="h-1.5 w-1.5 rounded-full bg-accent-primary chat-live-dot" />
            <span>Streaming live</span>
          </div>
        )}
      </div>

      {isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-tertiary text-content-secondary">
          <User className="h-4 w-4" />
        </div>
      )}
    </div>
  );
}

function processCitations(
  children: React.ReactNode,
  onClick: (num: number, sources?: any[]) => void,
  sources?: any[],
): React.ReactNode {
  if (!children) return children;

  return Array.isArray(children)
    ? children.map((child, i) => processSingleChild(child, onClick, i, sources))
    : processSingleChild(children, onClick, 0, sources);
}

function processSingleChild(
  child: React.ReactNode,
  onClick: (num: number, sources?: any[]) => void,
  key: number,
  sources?: any[],
): React.ReactNode {
  if (typeof child !== "string") return child;

  const parts = child.split(/(\[\d+\])/g);
  if (parts.length === 1) return child;

  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (match) {
      const num = parseInt(match[1], 10);
      return (
        <SourceCitation
          key={`${key}-${i}`}
          number={num}
          onClick={onClick}
          sources={sources}
        />
      );
    }
    return part;
  });
}

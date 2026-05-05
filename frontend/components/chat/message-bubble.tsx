"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, Copy, PencilLine, RefreshCcw, Trash2, User } from "lucide-react";
import { OverflowActionMenu } from "./overflow-action-menu";
import { SourceCitation } from "./source-citation";
import { ThinkingIndicator } from "./thinking-indicator";

interface MessageBubbleProps {
  message: {
    id: string;
    role: "user" | "assistant";
    content: string;
    sources?: any[];
    state?: "streaming" | "complete" | "error";
  };
  onCitationClick: (num: number, sources?: any[]) => void;
  onDelete?: (messageId: string) => void;
  onEditAndResend?: (messageId: string, content: string) => void;
  onRegenerate?: (messageId: string) => void;
  onCopy?: (content: string) => void;
  deleteDisabled?: boolean;
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
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {/* Avatar */}
      {!isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-primary/20 text-accent-primary">
          <Bot className="h-4 w-4" />
        </div>
      )}

      {/* Bubble */}
      <div
        className={`max-w-[85%] rounded-[24px] px-4 py-3 shadow-[0_18px_48px_rgba(2,6,23,0.22)] transition-all duration-200 ${
          isUser
            ? "rounded-br-md bg-linear-to-br from-accent-primary via-accent-secondary to-accent-primary-hover text-white"
            : isError
              ? "rounded-bl-md border border-red-500/30 bg-red-500/10 text-content-primary"
              : "rounded-bl-md border border-white/7 bg-white/[0.04] text-content-primary backdrop-blur-sm"
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
          <ThinkingIndicator compact />
        ) : (
          <div className="prose prose-sm prose-invert max-w-none text-content-primary">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                // Intercept citation patterns [1], [2] etc.
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
                    <code className="rounded bg-surface-secondary px-1.5 py-0.5 font-mono text-xs" {...props}>
                      {children}
                    </code>
                  ) : (
                    <code className={`${className} font-mono text-xs`} {...props}>
                      {children}
                    </code>
                  );
                },
                pre: ({ children, ...props }) => (
                  <pre
                    className="overflow-x-auto rounded-lg bg-surface-secondary p-3 font-mono text-xs"
                    {...props}
                  >
                    {children}
                  </pre>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-3 flex items-center gap-2 border-t border-white/8 pt-3 text-[11px] text-content-tertiary">
            <span className="inline-flex h-5 items-center rounded-full border border-accent-citation/20 bg-accent-citation/10 px-2 font-medium text-accent-citation">
              {message.sources.length} source{message.sources.length > 1 ? "s" : ""}
            </span>
            <span>Grounded answer</span>
          </div>
        )}
        {!isUser && isStreaming && message.content && (
          <div className="mt-3 flex items-center gap-2 text-[11px] text-content-tertiary">
            <span className="h-1.5 w-1.5 rounded-full bg-accent-primary chat-live-dot" />
            <span>Streaming live</span>
          </div>
        )}
      </div>

      {/* User avatar */}
      {isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-tertiary text-content-secondary">
          <User className="h-4 w-4" />
        </div>
      )}
    </div>
  );
}

/**
 * Replace citation patterns like [1], [2] in React children with SourceCitation components.
 */
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

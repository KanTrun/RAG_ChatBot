"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { Send, Paperclip } from "lucide-react";
import { StatusBadge } from "@/components/shared/status-badge";
import { apiUpload, getApiErrorMessage } from "@/lib/client-api";
import {
  pollUploadedDocumentStatus,
  type UploadedDocument,
} from "@/lib/document-upload";

type ChatResponseMode = "strict_documents" | "hybrid_general";

interface ChatInputProps {
  onSend: (message: string, responseMode: ChatResponseMode) => void;
  disabled?: boolean;
  onUploadComplete?: (document: UploadedDocument) => void;
  onUploadStatusChange?: (document: UploadedDocument) => void;
  responseMode: ChatResponseMode;
  onResponseModeChange: (responseMode: ChatResponseMode) => void;
  draftValue?: string;
  onDraftValueChange?: (value: string) => void;
  editLabel?: string | null;
  onCancelEdit?: () => void;
}

interface ChatUpload {
  fileName: string;
  status: "uploading" | "pending" | "processing" | "indexed" | "failed";
  error?: string;
  duplicateOfExisting?: boolean;
}

export function ChatInput({
  onSend,
  disabled,
  onUploadComplete,
  onUploadStatusChange,
  responseMode,
  onResponseModeChange,
  draftValue,
  onDraftValueChange,
  editLabel,
  onCancelEdit,
}: ChatInputProps) {
  const [localValue, setLocalValue] = useState("");
  const [uploads, setUploads] = useState<ChatUpload[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isControlled = typeof draftValue === "string" && typeof onDraftValueChange === "function";
  const value = isControlled ? draftValue : localValue;
  const setValue = isControlled ? onDraftValueChange : setLocalValue;

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  useEffect(() => {
    if (!editLabel) return;
    textareaRef.current?.focus();
  }, [editLabel]);

  const handleSubmit = useCallback(() => {
    if (!value.trim() || disabled) return;
    onSend(value.trim(), responseMode);
    setValue("");
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [value, disabled, onSend, responseMode]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function handleInput() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }

  const updateUpload = useCallback(
    (
      fileName: string,
      update: Partial<Pick<ChatUpload, "status" | "error" | "duplicateOfExisting">>,
    ) => {
      setUploads((prev) =>
        prev.map((item) =>
          item.fileName === fileName ? { ...item, ...update } : item,
        ),
      );
    },
    [],
  );

  const uploadFile = useCallback(
    async (file: File) => {
      const fileName = file.name;
      setUploads((prev) => [...prev, { fileName, status: "uploading" }]);

      try {
        const document = await apiUpload<UploadedDocument>("/api/v1/documents/upload", file);
        updateUpload(fileName, {
          status: document.status,
          duplicateOfExisting: document.duplicate_of_existing,
          error: undefined,
        });
        onUploadStatusChange?.(document);
        onUploadComplete?.(document);

        if (document.status === "pending" || document.status === "processing") {
          const settledDocument = await pollUploadedDocumentStatus(document.id, (nextDocument) => {
            updateUpload(fileName, {
              status: nextDocument.status,
              duplicateOfExisting: nextDocument.duplicate_of_existing,
              error: nextDocument.error_message || undefined,
            });
            onUploadStatusChange?.(nextDocument);
          });

          if (settledDocument?.error_message) {
            updateUpload(fileName, { error: settledDocument.error_message });
          }
        }
      } catch (error) {
        updateUpload(fileName, { status: "failed", error: getApiErrorMessage(error) });
      }
    },
    [onUploadComplete, onUploadStatusChange, updateUpload],
  );

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(e.target.files || []);
    selected.forEach((file) => void uploadFile(file));
    e.target.value = "";
  }

  return (
    <div className="border-t border-border-primary bg-surface-primary px-4 py-3">
      {editLabel && (
        <div className="mx-auto mb-2 flex max-w-3xl items-center justify-between gap-3 rounded-2xl border border-accent-primary/20 bg-accent-primary/10 px-3 py-2 text-sm text-content-primary">
          <div>
            <p className="font-medium">{editLabel}</p>
            <p className="text-xs text-content-secondary">
              Gửi lại sẽ thay thế đoạn chat cũ bằng câu hỏi mới.
            </p>
          </div>
          <button
            type="button"
            onClick={onCancelEdit}
            className="rounded-xl border border-border-primary px-3 py-2 text-xs font-medium text-content-secondary transition-colors hover:bg-surface-tertiary hover:text-content-primary"
          >
            Hủy
          </button>
        </div>
      )}
      <div className="mx-auto mb-2 flex max-w-3xl items-center justify-between gap-3 rounded-2xl border border-border-primary bg-surface-secondary/80 px-3 py-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onResponseModeChange("strict_documents")}
            aria-pressed={responseMode === "strict_documents"}
            disabled={disabled}
            className={`rounded-xl px-3 py-1.5 text-xs font-medium transition-all ${
              responseMode === "strict_documents"
                ? "bg-content-primary text-surface-primary shadow-sm"
                : "text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
            } disabled:opacity-50`}
          >
            Document only
          </button>
          <button
            type="button"
            onClick={() => onResponseModeChange("hybrid_general")}
            aria-pressed={responseMode === "hybrid_general"}
            disabled={disabled}
            className={`rounded-xl px-3 py-1.5 text-xs font-medium transition-all ${
              responseMode === "hybrid_general"
                ? "bg-content-primary text-surface-primary shadow-sm"
                : "text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
            } disabled:opacity-50`}
          >
            Allow outside knowledge
          </button>
        </div>
        <p className="text-right text-[11px] leading-4 text-content-tertiary">
          {responseMode === "strict_documents"
            ? "Default: only grounded document evidence is allowed."
            : "Outside knowledge is enabled when document support is weak."}
        </p>
      </div>

      <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-xl border border-border-primary bg-surface-secondary px-3 py-2">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          className="mb-0.5 rounded-xl p-2 text-content-tertiary transition-all duration-200 hover:bg-surface-tertiary hover:text-content-secondary disabled:opacity-50"
          aria-label="Attach file"
        >
          <Paperclip className="h-4 w-4" />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.md,.html"
          onChange={handleFileSelect}
          className="hidden"
        />

        <textarea
          ref={textareaRef}
          id="chat-input"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          placeholder={
            responseMode === "strict_documents"
              ? "Ask about your documents. Outside knowledge is off by default."
              : "Ask anything. I will use your documents first, then outside knowledge if needed."
          }
          rows={1}
          disabled={disabled}
          className="max-h-[200px] flex-1 resize-none bg-transparent text-sm text-content-primary placeholder:text-content-tertiary focus:outline-none disabled:opacity-50"
        />

        <button
          onClick={handleSubmit}
          disabled={!value.trim() || disabled}
          className="mb-0.5 rounded-xl bg-linear-to-br from-accent-primary via-accent-secondary to-accent-primary-hover p-2 text-white shadow-[0_12px_30px_rgba(99,102,241,0.28)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_18px_36px_rgba(99,102,241,0.34)] disabled:translate-y-0 disabled:opacity-30"
          aria-label={editLabel ? "Resend edited message" : "Send message"}
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
      <p className="mx-auto mt-1.5 max-w-3xl text-center text-xs text-content-tertiary">
        Press <kbd className="rounded border border-border-primary px-1">Enter</kbd> to send,{" "}
        <kbd className="rounded border border-border-primary px-1">Shift+Enter</kbd> for new line
      </p>
      {uploads.length > 0 && (
        <ul className="mx-auto mt-2 max-w-3xl space-y-1" aria-live="polite">
          {uploads.slice(-3).map((item, index) => (
            <li
              key={`${item.fileName}-${index}`}
              className="flex items-center gap-2 rounded-lg border border-border-primary bg-surface-secondary px-3 py-1.5 text-xs"
            >
              <span className="min-w-0 flex-1 truncate text-content-secondary">
                {item.fileName}
                {item.duplicateOfExisting ? " (already uploaded)" : ""}
              </span>
              <StatusBadge status={item.status === "uploading" ? "processing" : item.status} />
              {item.error && (
                <span className="max-w-44 truncate text-red-400" title={item.error}>
                  {item.error}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

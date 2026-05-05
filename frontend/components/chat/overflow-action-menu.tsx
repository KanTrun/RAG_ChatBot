"use client";

import { useEffect, useId, useRef, useState } from "react";
import { MoreHorizontal, type LucideIcon } from "lucide-react";

interface OverflowActionItem {
  label: string;
  icon?: LucideIcon;
  destructive?: boolean;
  disabled?: boolean;
  onSelect: () => void;
}

interface OverflowActionMenuProps {
  buttonLabel: string;
  items: OverflowActionItem[];
  align?: "left" | "right";
  disabled?: boolean;
}

export function OverflowActionMenu({
  buttonLabel,
  items,
  align = "right",
  disabled = false,
}: OverflowActionMenuProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const renderedItems = items.filter(Boolean);

  useEffect(() => {
    if (!open) return;

    function handlePointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleEscape);
    };
  }, [open]);

  if (renderedItems.length === 0) {
    return null;
  }

  return (
    <div ref={containerRef} className="relative shrink-0">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        aria-label={buttonLabel}
        aria-haspopup="menu"
        aria-controls={menuId}
        aria-expanded={open}
        className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-xl border border-border-primary bg-surface-secondary/80 text-content-tertiary transition-colors hover:bg-surface-tertiary hover:text-content-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/50 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          className={`absolute top-[calc(100%+0.5rem)] z-20 min-w-52 overflow-hidden rounded-2xl border border-white/10 bg-surface-secondary p-1 shadow-lg ${
            align === "left" ? "left-0" : "right-0"
          }`}
        >
          {renderedItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.label}
                type="button"
                role="menuitem"
                disabled={item.disabled}
                onClick={() => {
                  item.onSelect();
                  setOpen(false);
                }}
                className={`flex min-h-11 w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/50 disabled:cursor-not-allowed disabled:opacity-50 ${
                  item.destructive
                    ? "text-red-300 hover:bg-red-500/10"
                    : "text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
                }`}
              >
                {Icon ? <Icon className="h-4 w-4" /> : null}
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

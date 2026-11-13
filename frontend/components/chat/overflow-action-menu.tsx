"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
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
  const [coords, setCoords] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const menuId = useId();
  const renderedItems = items.filter(Boolean);

  const updateMenuPosition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const menuWidth = 220;
    const estimatedMenuHeight = Math.max(96, renderedItems.length * 46 + 16);
    const viewportW = window.innerWidth || 1024;
    const viewportH = window.innerHeight || 768;

    let left = align === "left" ? rect.left : rect.right - menuWidth;
    if (left + menuWidth > viewportW - 12) {
      left = Math.max(12, viewportW - menuWidth - 12);
    }
    if (left < 12) {
      left = 12;
    }

    const spaceBelow = viewportH - rect.bottom;
    const shouldFlipUp = spaceBelow < estimatedMenuHeight && rect.top > estimatedMenuHeight;
    const top = shouldFlipUp
      ? Math.max(12, rect.top - estimatedMenuHeight - 6)
      : rect.bottom + 6;

    setCoords({ top, left });
  }, [align, renderedItems.length]);

  useEffect(() => {
    if (!open) return;
    updateMenuPosition();

    function handlePointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (
        !triggerRef.current?.contains(target) &&
        !menuRef.current?.contains(target)
      ) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
        return;
      }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const enabledButtons = itemRefs.current.filter(
          (btn): btn is HTMLButtonElement => Boolean(btn && !btn.disabled),
        );
        if (enabledButtons.length === 0) return;
        const currentIndex = enabledButtons.indexOf(
          document.activeElement as HTMLButtonElement,
        );
        const delta = event.key === "ArrowDown" ? 1 : -1;
        const nextIndex =
          currentIndex === -1
            ? 0
            : (currentIndex + delta + enabledButtons.length) % enabledButtons.length;
        enabledButtons[nextIndex]?.focus();
      }
    }

    function handleScrollOrResize() {
      updateMenuPosition();
    }

    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("resize", handleScrollOrResize);
    window.addEventListener("scroll", handleScrollOrResize, true);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("resize", handleScrollOrResize);
      window.removeEventListener("scroll", handleScrollOrResize, true);
    };
  }, [open, updateMenuPosition]);

  if (renderedItems.length === 0) {
    return null;
  }

  const menuElement = open ? (
    <div
      ref={menuRef}
      id={menuId}
      role="menu"
      style={{ top: `${coords.top}px`, left: `${coords.left}px` }}
      className="fixed z-50 min-w-52 overflow-hidden rounded-2xl border border-border-primary bg-surface-secondary p-1.5 shadow-2xl animate-scale-pop"
    >
      {renderedItems.map((item, idx) => {
        const Icon = item.icon;
        return (
          <button
            key={item.label}
            ref={(el) => {
              itemRefs.current[idx] = el;
            }}
            type="button"
            role="menuitem"
            disabled={item.disabled}
            onClick={(event) => {
              event.stopPropagation();
              setOpen(false);
              item.onSelect();
            }}
            className={`flex min-h-10 w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/50 disabled:cursor-not-allowed disabled:opacity-50 ${
              item.destructive
                ? "text-red-400 hover:bg-red-500/10"
                : "text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
            }`}
          >
            {Icon ? <Icon className="h-4 w-4 shrink-0" /> : null}
            <span className="truncate">{item.label}</span>
          </button>
        );
      })}
    </div>
  ) : null;

  return (
    <div className="relative shrink-0">
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((current) => !current);
        }}
        aria-label={buttonLabel}
        aria-haspopup="menu"
        aria-controls={menuId}
        aria-expanded={open}
        className="inline-flex min-h-9 min-w-9 items-center justify-center rounded-xl border border-border-primary bg-surface-secondary/80 text-content-tertiary transition-colors hover:bg-surface-tertiary hover:text-content-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/50 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>
      {open && typeof document !== "undefined"
        ? createPortal(menuElement, document.body)
        : menuElement}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { LogOut, Moon, Sun } from "lucide-react";
import { signOut, useSession } from "next-auth/react";

export function AuthenticatedUserFooter() {
  const { data: session } = useSession();
  const email = session?.user?.email ?? "Signed in";
  const roles = session?.roles ?? session?.user?.roles ?? [];
  const isAdmin = roles.includes("admin");
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("rag-ui-theme");
      if (saved === "light" || saved === "dark") {
        setTheme(saved);
        document.documentElement.dataset.theme = saved;
      }
    } catch {
      // ignore storage errors
    }
  }, []);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try {
      window.localStorage.setItem("rag-ui-theme", next);
    } catch {
      // ignore storage errors
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-xs font-medium text-content-primary">{email}</p>
          <span className="mt-1 inline-flex rounded-full border border-border-primary px-2 py-0.5 text-[11px] font-medium text-content-tertiary">
            {isAdmin ? "Admin" : "User"}
          </span>
        </div>
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          title={theme === "dark" ? "Chuyển sang giao diện Sáng" : "Chuyển sang giao diện Tối"}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border-primary bg-surface-primary text-content-secondary transition-colors hover:bg-surface-tertiary hover:text-content-primary"
        >
          {theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
        </button>
      </div>
      <button
        type="button"
        onClick={() => signOut({ callbackUrl: "/login" })}
        className="flex w-full items-center justify-center gap-2 rounded-lg border border-border-primary px-3 py-2 text-xs font-medium text-content-secondary transition-colors hover:bg-surface-tertiary hover:text-content-primary"
      >
        <LogOut className="h-3.5 w-3.5" />
        Logout
      </button>
    </div>
  );
}

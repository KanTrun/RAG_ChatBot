"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, MessageSquare } from "lucide-react";
import { ThemeToggle } from "@/components/shared/theme-toggle";
import { AuthenticatedUserFooter } from "@/components/shared/authenticated-user-footer";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-screen overflow-hidden bg-surface-primary">
      {/* Sidebar nav */}
      <aside className="flex w-56 flex-col border-r border-border-primary bg-surface-secondary">
        <div className="border-b border-border-primary px-4 py-4">
          <h1 className="text-sm font-bold text-content-primary">RAG Admin</h1>
        </div>
        <nav className="flex-1 p-2">
          <Link
            href="/admin"
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
              pathname === "/admin"
                ? "bg-accent-primary/10 font-medium text-accent-primary"
                : "text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
            }`}
          >
            <LayoutDashboard className="h-4 w-4" />
            Dashboard
          </Link>
          <Link
            href="/chat"
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
          >
            <MessageSquare className="h-4 w-4" />
            Back to Chat
          </Link>
        </nav>
        <div className="border-t border-border-primary p-3">
          <AuthenticatedUserFooter />
          <div className="mt-3">
          <ThemeToggle />
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-7xl px-6 py-6">{children}</div>
      </main>
    </div>
  );
}

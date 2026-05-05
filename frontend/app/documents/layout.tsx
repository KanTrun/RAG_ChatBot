"use client";

import { Suspense, useEffect, useState } from "react";
import { ChatSidebar } from "@/components/chat/chat-sidebar";

export default function DocumentsLayout({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div className="flex h-screen overflow-hidden bg-surface-primary" suppressHydrationWarning>
        <div className="w-16 shrink-0 border-r border-border-primary bg-surface-secondary" />
        <main className="flex flex-1 items-center justify-center text-sm text-content-tertiary">
          Loading documents...
        </main>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-surface-primary">
      <Suspense fallback={<div className="w-16 shrink-0 border-r border-border-primary bg-surface-secondary" />}>
        <ChatSidebar open={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />
      </Suspense>
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-7xl px-6 py-6">{children}</div>
      </main>
    </div>
  );
}

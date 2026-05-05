"use client";

import { Suspense, useEffect, useState } from "react";
import { ChatSidebar } from "@/components/chat/chat-sidebar";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div className="flex h-screen overflow-hidden bg-surface-primary" suppressHydrationWarning>
        <div className="w-16 shrink-0 border-r border-border-primary bg-surface-secondary" />
        <main className="flex flex-1 flex-col overflow-hidden">
          <div className="flex flex-1 items-center justify-center text-sm text-content-tertiary">
            Loading chat...
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-surface-primary">
      {/* Sidebar */}
      <Suspense fallback={<div className="w-16 shrink-0 border-r border-border-primary bg-surface-secondary" />}>
        <ChatSidebar open={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />
      </Suspense>

      {/* Main content */}
      <main className="flex flex-1 flex-col overflow-hidden">{children}</main>
    </div>
  );
}

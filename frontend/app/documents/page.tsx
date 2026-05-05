"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { UploadZone } from "@/components/admin/upload-zone";
import { DocumentTable } from "@/components/admin/document-table";
import { DocumentIndexingGuide } from "@/components/admin/document-indexing-guide";

export default function MyDocumentsPage() {
  const [refreshKey, setRefreshKey] = useState(0);
  const router = useRouter();

  function handleStartChat(documentIds: string[]) {
    if (documentIds.length === 0) return;
    const params = new URLSearchParams({ documentIds: documentIds.join(",") });
    router.push(`/chat?${params.toString()}`);
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-content-primary">My documents</h1>
        <p className="mt-1 text-sm text-content-secondary">
          Upload, re-index, remove, and start chats scoped to one or more documents.
        </p>
      </div>

      <DocumentIndexingGuide />

      <div className="grid gap-8 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <UploadZone
            title="Upload to my documents"
            onUploadComplete={() => setRefreshKey((key) => key + 1)}
          />
        </div>
        <div className="lg:col-span-2">
          <DocumentTable
            key={refreshKey}
            mode="user"
            title="My documents"
            onChanged={() => setRefreshKey((key) => key + 1)}
            onStartChat={handleStartChat}
          />
        </div>
      </div>
    </div>
  );
}

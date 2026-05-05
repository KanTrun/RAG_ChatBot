"use client";

import { useEffect, useState } from "react";
import { ShieldAlert } from "lucide-react";
import { StatsCards } from "@/components/admin/stats-cards";
import { UploadZone } from "@/components/admin/upload-zone";
import { DocumentTable } from "@/components/admin/document-table";
import { IngestionStatus } from "@/components/admin/ingestion-status";
import { ApiError, apiJson, getApiErrorMessage } from "@/lib/client-api";

interface Stats {
  total_documents: number;
  total_chunks: number;
  total_conversations: number;
  total_messages: number;
  docs_by_status: Record<string, number>;
}

export default function AdminDashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [accessDenied, setAccessDenied] = useState(false);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [checkedAccess, setCheckedAccess] = useState(false);

  useEffect(() => {
    setCheckedAccess(false);
    setError("");
    apiJson<Stats>("/api/v1/admin/stats")
      .then((data) => {
        setStats(data);
        setAccessDenied(false);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 403) {
          setAccessDenied(true);
          return;
        }
        setError(getApiErrorMessage(err));
      })
      .finally(() => setCheckedAccess(true));
  }, [refreshKey]);

  if (accessDenied) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="max-w-md rounded-xl border border-border-primary bg-surface-secondary px-6 py-8 text-center">
          <ShieldAlert className="mx-auto h-10 w-10 text-accent-warning" />
          <h1 className="mt-4 text-xl font-semibold text-content-primary">
            Admin access required
          </h1>
          <p className="mt-2 text-sm text-content-secondary">
            Sign in with an admin account to manage documents and monitor ingestion.
          </p>
        </div>
      </div>
    );
  }

  if (!checkedAccess) {
    return (
      <div className="py-12 text-center text-sm text-content-tertiary">
        Loading admin dashboard...
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-content-primary">Dashboard</h1>
        <p className="mt-1 text-sm text-content-secondary">
          Manage documents, monitor ingestion, and review system stats
        </p>
        {error && (
          <p role="alert" className="mt-3 text-sm text-red-400">
            {error}
          </p>
        )}
      </div>

      <StatsCards stats={stats} />

      <div className="grid gap-8 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <UploadZone onUploadComplete={() => setRefreshKey((k) => k + 1)} />
        </div>
        <div className="lg:col-span-2">
          <IngestionStatus enabled={checkedAccess && !accessDenied} />
        </div>
      </div>

      <DocumentTable
        key={refreshKey}
        mode="admin"
        title="All documents"
        onChanged={() => setRefreshKey((k) => k + 1)}
      />
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/shared/status-badge";
import { ApiError, apiJson } from "@/lib/client-api";

interface Job {
  document_id: string;
  title: string;
  status: string;
  created_at: string;
  error_message: string | null;
}

export function IngestionStatus({ enabled = true }: { enabled?: boolean }) {
  const [jobs, setJobs] = useState<Job[]>([]);

  useEffect(() => {
    if (!enabled) return;
    let forbidden = false;
    fetchJobs();
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);

    function fetchJobs() {
      if (forbidden) return;
      apiJson<Job[]>("/api/v1/admin/ingestion-status")
        .then((data) => setJobs(Array.isArray(data) ? data : []))
        .catch((error) => {
          if (error instanceof ApiError && error.status === 403) forbidden = true;
          setJobs([]);
        });
    }
  }, [enabled]);

  if (jobs.length === 0) {
    return (
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-content-primary">Ingestion Status</h3>
        <p className="rounded-xl border border-border-primary bg-surface-secondary px-4 py-8 text-center text-xs text-content-tertiary">
          No active ingestion jobs
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-content-primary">Ingestion Status</h3>
      <ul className="space-y-2">
        {jobs.map((job) => (
          <li
            key={job.document_id}
            className="rounded-lg border border-border-primary bg-surface-secondary px-4 py-3"
          >
            <div className="flex items-center justify-between">
              <span className="truncate text-sm font-medium text-content-primary">
                {job.title}
              </span>
              <StatusBadge status={job.status} />
            </div>
            {job.error_message && (
              <p className="mt-1 truncate text-xs text-red-400">{job.error_message}</p>
            )}
            {job.status === "processing" && (
              <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-surface-tertiary">
                <div className="h-full w-1/2 animate-pulse rounded-full bg-accent-primary" />
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

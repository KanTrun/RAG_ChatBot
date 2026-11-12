"use client";

import { useEffect, useState } from "react";
import { Award, Lock, Play, ShieldAlert, Unlock, Users } from "lucide-react";
import { StatsCards, type Stats } from "@/components/admin/stats-cards";
import { UploadZone } from "@/components/admin/upload-zone";
import { DocumentTable } from "@/components/admin/document-table";
import { IngestionStatus } from "@/components/admin/ingestion-status";
import { ApiError, apiJson, getApiErrorMessage } from "@/lib/client-api";

interface AdminUser {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  is_superuser: boolean;
  roles: string[];
  document_count: number;
  created_at: string | null;
}

interface EvaluationRun {
  run_id: string;
  timestamp: string;
  total_questions: number;
  faithfulness: number;
  context_precision: number;
  context_recall: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  avg_tokens_per_answer: number;
  bm25_enabled: boolean;
}

interface EvaluationDashboard {
  latest: EvaluationRun | null;
  history: EvaluationRun[];
}

export default function AdminDashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [evaluations, setEvaluations] = useState<EvaluationDashboard | null>(null);
  const [runningEval, setRunningEval] = useState(false);
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
        void apiJson<AdminUser[]>("/api/v1/admin/users")
          .then((userList) => setUsers(Array.isArray(userList) ? userList : []))
          .catch(() => {});
        void apiJson<EvaluationDashboard>("/api/v1/admin/evaluations")
          .then((evalData) => setEvaluations(evalData))
          .catch(() => {});
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

  async function handleRoleChange(userId: string, role: string) {
    try {
      const updated = await apiJson<AdminUser>(`/api/v1/admin/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ role }),
      });
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)));
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  }

  async function handleToggleUserActive(user: AdminUser) {
    try {
      const updated = await apiJson<AdminUser>(`/api/v1/admin/users/${user.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !user.is_active }),
      });
      setUsers((prev) => prev.map((u) => (u.id === user.id ? updated : u)));
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  }

  async function handleRunEvaluation() {
    setRunningEval(true);
    setError("");
    try {
      const result = await apiJson<EvaluationDashboard>("/api/v1/admin/evaluations/run", {
        method: "POST",
      });
      setEvaluations(result);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setRunningEval(false);
    }
  }

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
          Manage users, documents, monitor ingestion, and review RAG quality evaluation benchmarks
        </p>
        {error && (
          <p role="alert" className="mt-3 text-sm text-red-400">
            {error}
          </p>
        )}
      </div>

      <StatsCards stats={stats} />

      {/* Quality Evaluation Benchmark & History */}
      <div className="rounded-xl border border-border-primary bg-surface-secondary p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Award className="h-5 w-5 text-accent-primary" />
            <div>
              <h3 className="text-sm font-semibold text-content-primary">
                RAG Quality Evaluation (Golden Dataset Benchmark)
              </h3>
              <p className="text-xs text-content-tertiary">
                Measured Faithfulness, Context Precision/Recall, Latency p50/p95, and Token Efficiency over time
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void handleRunEvaluation()}
            disabled={runningEval}
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent-primary px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-primary-hover disabled:opacity-50"
          >
            <Play className="h-3.5 w-3.5" />
            <span>{runningEval ? "Running Evaluation..." : "Run Evaluation Now"}</span>
          </button>
        </div>

        {evaluations?.latest ? (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <div className="rounded-lg border border-border-primary bg-surface-primary p-3">
                <p className="text-[11px] uppercase text-content-tertiary">Faithfulness</p>
                <p className="mt-1 text-lg font-bold text-green-400">
                  {(evaluations.latest.faithfulness * 100).toFixed(1)}%
                </p>
              </div>
              <div className="rounded-lg border border-border-primary bg-surface-primary p-3">
                <p className="text-[11px] uppercase text-content-tertiary">Context Precision</p>
                <p className="mt-1 text-lg font-bold text-accent-primary">
                  {(evaluations.latest.context_precision * 100).toFixed(1)}%
                </p>
              </div>
              <div className="rounded-lg border border-border-primary bg-surface-primary p-3">
                <p className="text-[11px] uppercase text-content-tertiary">Context Recall</p>
                <p className="mt-1 text-lg font-bold text-teal-400">
                  {(evaluations.latest.context_recall * 100).toFixed(1)}%
                </p>
              </div>
              <div className="rounded-lg border border-border-primary bg-surface-primary p-3">
                <p className="text-[11px] uppercase text-content-tertiary">Latency p50 / p95</p>
                <p className="mt-1 text-sm font-bold text-content-primary">
                  {evaluations.latest.latency_p50_ms} / {evaluations.latest.latency_p95_ms} ms
                </p>
              </div>
              <div className="rounded-lg border border-border-primary bg-surface-primary p-3">
                <p className="text-[11px] uppercase text-content-tertiary">Avg Tokens / Answer</p>
                <p className="mt-1 text-lg font-bold text-content-primary">
                  {evaluations.latest.avg_tokens_per_answer}
                </p>
              </div>
              <div className="rounded-lg border border-border-primary bg-surface-primary p-3">
                <p className="text-[11px] uppercase text-content-tertiary">Golden Questions</p>
                <p className="mt-1 text-lg font-bold text-content-primary">
                  {evaluations.latest.total_questions}
                </p>
              </div>
            </div>

            {evaluations.history.length > 0 && (
              <div className="overflow-x-auto rounded-lg border border-border-primary">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border-primary bg-surface-primary text-left text-[11px] uppercase text-content-tertiary">
                      <th className="px-3 py-2">Run ID</th>
                      <th className="px-3 py-2">Timestamp</th>
                      <th className="px-3 py-2">Questions</th>
                      <th className="px-3 py-2">Faithfulness</th>
                      <th className="px-3 py-2">Precision</th>
                      <th className="px-3 py-2">Recall</th>
                      <th className="px-3 py-2">p50 / p95 (ms)</th>
                      <th className="px-3 py-2">Avg Tokens</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-primary">
                    {evaluations.history.map((run) => (
                      <tr key={run.run_id} className="hover:bg-surface-primary/60">
                        <td className="px-3 py-2 font-mono text-content-primary">{run.run_id}</td>
                        <td className="px-3 py-2 text-content-secondary">
                          {new Date(run.timestamp).toLocaleString()}
                        </td>
                        <td className="px-3 py-2 text-content-secondary">{run.total_questions}</td>
                        <td className="px-3 py-2 font-medium text-green-400">
                          {(run.faithfulness * 100).toFixed(1)}%
                        </td>
                        <td className="px-3 py-2 text-content-primary">
                          {(run.context_precision * 100).toFixed(1)}%
                        </td>
                        <td className="px-3 py-2 text-content-primary">
                          {(run.context_recall * 100).toFixed(1)}%
                        </td>
                        <td className="px-3 py-2 font-mono text-content-secondary">
                          {run.latency_p50_ms} / {run.latency_p95_ms}
                        </td>
                        <td className="px-3 py-2 font-mono text-content-secondary">
                          {run.avg_tokens_per_answer}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : (
          <p className="text-xs text-content-tertiary">
            No evaluation runs recorded yet. Click &quot;Run Evaluation Now&quot; or run{" "}
            <code>python scripts/run_evaluation.py</code>.
          </p>
        )}
      </div>

      {/* User Management */}
      {users.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-accent-primary" />
            <h3 className="text-sm font-semibold text-content-primary">User Management</h3>
          </div>
          <div className="overflow-x-auto rounded-xl border border-border-primary">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-primary bg-surface-secondary text-left text-xs font-medium uppercase tracking-wider text-content-tertiary">
                  <th className="px-4 py-3">User</th>
                  <th className="px-4 py-3">Role</th>
                  <th className="px-4 py-3">Documents</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-primary">
                {users.map((u) => {
                  const primaryRole = u.roles[0] || (u.is_superuser ? "admin" : "viewer");
                  return (
                    <tr key={u.id} className="hover:bg-surface-secondary">
                      <td className="px-4 py-3">
                        <p className="font-medium text-content-primary">{u.display_name}</p>
                        <p className="text-xs text-content-tertiary">{u.email}</p>
                      </td>
                      <td className="px-4 py-3">
                        <select
                          value={primaryRole}
                          onChange={(e) => void handleRoleChange(u.id, e.target.value)}
                          aria-label={`Change role for ${u.email}`}
                          className="rounded-lg border border-border-primary bg-surface-secondary px-2.5 py-1 text-xs text-content-primary"
                        >
                          <option value="admin">admin</option>
                          <option value="editor">editor</option>
                          <option value="viewer">viewer</option>
                        </select>
                      </td>
                      <td className="px-4 py-3 text-content-secondary">{u.document_count}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                            u.is_active
                              ? "bg-green-500/15 text-green-400"
                              : "bg-red-500/15 text-red-400"
                          }`}
                        >
                          {u.is_active ? "Active" : "Locked"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() => void handleToggleUserActive(u)}
                          className="inline-flex items-center gap-1 rounded-lg border border-border-primary px-2.5 py-1 text-xs text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
                        >
                          {u.is_active ? (
                            <>
                              <Lock className="h-3 w-3 text-red-400" />
                              <span>Lock</span>
                            </>
                          ) : (
                            <>
                              <Unlock className="h-3 w-3 text-green-400" />
                              <span>Unlock</span>
                            </>
                          )}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

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

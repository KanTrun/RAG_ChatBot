"use client";

import { FileText, Database, Clock, Activity, HelpCircle, ShieldOff } from "lucide-react";

export interface Stats {
  total_documents: number;
  total_chunks: number;
  total_conversations: number;
  total_messages: number;
  docs_by_status: Record<string, number>;
  total_questions?: number;
  abstention_rate?: number;
  avg_latency_ms?: number;
  avg_tokens_per_answer?: number;
}

interface StatsCardsProps {
  stats: Stats | null;
}

export function StatsCards({ stats }: StatsCardsProps) {
  const cards = [
    {
      label: "Total Documents",
      value: stats?.total_documents ?? "—",
      icon: FileText,
    },
    {
      label: "Total Chunks",
      value: stats?.total_chunks ?? "—",
      icon: Database,
    },
    {
      label: "Questions Asked",
      value: stats?.total_questions ?? stats?.total_conversations ?? "—",
      icon: HelpCircle,
    },
    {
      label: "Abstention Rate",
      value:
        stats?.abstention_rate !== undefined
          ? `${(stats.abstention_rate * 100).toFixed(1)}%`
          : "0.0%",
      icon: ShieldOff,
    },
    {
      label: "Avg Latency",
      value:
        stats?.avg_latency_ms !== undefined && stats.avg_latency_ms > 0
          ? `${Math.round(stats.avg_latency_ms)} ms`
          : "—",
      icon: Clock,
    },
    {
      label: "Pipeline Health",
      value: stats ? "Healthy" : "—",
      icon: Activity,
      isHealth: true,
    },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {cards.map((card) => (
        <div
          key={card.label}
          className="rounded-xl border border-border-primary bg-surface-secondary p-5"
        >
          <div className="flex items-start justify-between">
            <p className="text-xs font-medium uppercase tracking-wider text-content-tertiary">
              {card.label}
            </p>
            <card.icon className="h-4 w-4 text-content-tertiary" />
          </div>
          <p className="mt-2 text-2xl font-bold text-content-primary">
            {card.isHealth && stats ? (
              <span className="flex items-center gap-2 text-lg">
                <span className="h-2 w-2 rounded-full bg-green-400" />
                Healthy
              </span>
            ) : typeof card.value === "number" ? (
              card.value.toLocaleString()
            ) : (
              card.value
            )}
          </p>
        </div>
      ))}
    </div>
  );
}

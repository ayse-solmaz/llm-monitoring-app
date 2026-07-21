"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import DecisionBadge, { apiScoreToScoreResult } from "@/components/DecisionBadge";
import ScoreCard from "@/components/chat/ScoreCard";
import {
  fetchMetricsSummary,
  fetchScoresSummary,
  fetchSessionDetail,
  fetchSessions,
} from "@/lib/llm-api";
import type {
  ApiSession,
  ApiSessionDetail,
  MetricsSummary,
  ScoresSummary,
} from "@/lib/types";

const DECISION_COLORS = {
  accept: "#16a34a",
  review: "#d97706",
  reject: "#dc2626",
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

function sessionLabel(session: ApiSession, index: number): string {
  const shortId = session.id.slice(0, 8);
  return `#${index + 1} ${shortId}`;
}

export default function DashboardView() {
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [total, setTotal] = useState(0);
  const [sessions, setSessions] = useState<ApiSession[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ApiSessionDetail | null>(null);
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [scores, setScores] = useState<ScoresSummary | null>(null);
  const [throughputSeries, setThroughputSeries] = useState<
    Array<{ label: string; avgTokensPerSec: number }>
  >([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSummaries = useCallback(async () => {
    const [metricsData, scoresData] = await Promise.all([
      fetchMetricsSummary(),
      fetchScoresSummary(),
    ]);
    setMetrics(metricsData);
    setScores(scoresData);
  }, []);

  const loadSessions = useCallback(async () => {
    const data = await fetchSessions(page, limit);
    setSessions(data.sessions);
    setTotal(data.total);
    return data.sessions;
  }, [page, limit]);

  const loadThroughputSeries = useCallback(async (items: ApiSession[]) => {
    if (items.length === 0) {
      setThroughputSeries([]);
      return;
    }

    const details = await Promise.all(
      items.map((session) => fetchSessionDetail(session.id))
    );

    const series = details
      .map((sessionDetail, index) => {
        const assistant = sessionDetail.messages.filter(
          (m) => m.role === "assistant" && m.tokens_per_sec > 0
        );
        const avg =
          assistant.length > 0
            ? assistant.reduce((sum, m) => sum + m.tokens_per_sec, 0) /
              assistant.length
            : 0;
        return {
          label: sessionLabel(items[index], index),
          avgTokensPerSec: Math.round(avg * 10) / 10,
          createdAt: sessionDetail.created_at,
        };
      })
      .sort(
        (a, b) =>
          new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()
      )
      .map(({ label, avgTokensPerSec }) => ({ label, avgTokensPerSec }));

    setThroughputSeries(series);
  }, []);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const items = await loadSessions();
        await loadSummaries();
        if (!cancelled) {
          await loadThroughputSeries(items);
          if (items.length > 0) {
            setSelectedId(items[0].id);
          } else {
            setSelectedId(null);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load dashboard");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [loadSessions, loadSummaries, loadThroughputSeries]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }

    let cancelled = false;
    void fetchSessionDetail(selectedId)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load session");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const totalPages = Math.max(1, Math.ceil(total / limit));

  const decisionChartData = scores
    ? (["accept", "review", "reject"] as const).map((key) => ({
        name: key,
        count: scores.by_decision[key] ?? 0,
      }))
    : [];

  if (loading) {
    return <p className="text-sm text-gray-500">Loading dashboard…</p>;
  }

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  return (
    <div className="max-w-6xl mx-auto flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <p className="text-sm text-gray-600">
          Session history, metrics, and decision scoring summaries
        </p>
      </div>

      {metrics && (
        <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label="Sessions" value={String(metrics.session_count)} />
          <StatCard
            label="Avg TTFT"
            value={
              metrics.avg_ttft_ms !== null
                ? `${Math.round(metrics.avg_ttft_ms)} ms`
                : "—"
            }
          />
          <StatCard
            label="Avg tok/s"
            value={
              metrics.avg_tokens_per_sec !== null
                ? metrics.avg_tokens_per_sec.toFixed(1)
                : "—"
            }
          />
          <StatCard label="Total tokens" value={String(metrics.total_tokens)} />
        </section>
      )}

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Avg tokens/sec by session">
          {throughputSeries.length === 0 ? (
            <p className="text-sm text-gray-400 p-4">No session data yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={throughputSeries}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="avgTokensPerSec"
                  stroke="#2563eb"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Decision distribution">
          {decisionChartData.every((d) => d.count === 0) ? (
            <p className="text-sm text-gray-400 p-4">No scores yet.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie
                    data={decisionChartData}
                    dataKey="count"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={70}
                    label
                  >
                    {decisionChartData.map((entry) => (
                      <Cell
                        key={entry.name}
                        fill={
                          DECISION_COLORS[
                            entry.name as keyof typeof DECISION_COLORS
                          ]
                        }
                      />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={decisionChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Bar dataKey="count">
                    {decisionChartData.map((entry) => (
                      <Cell
                        key={entry.name}
                        fill={
                          DECISION_COLORS[
                            entry.name as keyof typeof DECISION_COLORS
                          ]
                        }
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          {scores?.avg_composite !== null && scores?.avg_composite !== undefined && (
            <p className="text-xs text-gray-500 px-4 pb-3">
              Avg composite score: {scores.avg_composite}
            </p>
          )}
        </ChartCard>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-4">
        <section className="rounded border bg-white">
          <div className="border-b px-4 py-3">
            <h2 className="text-sm font-semibold">Sessions</h2>
          </div>
          <ul className="divide-y max-h-[420px] overflow-y-auto">
            {sessions.length === 0 && (
              <li className="p-4 text-sm text-gray-400">No sessions yet.</li>
            )}
            {sessions.map((session) => (
              <li key={session.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(session.id)}
                  className={`w-full text-left px-4 py-3 text-sm hover:bg-gray-50 ${
                    selectedId === session.id ? "bg-blue-50" : ""
                  }`}
                >
                  <p className="font-medium truncate">{session.model_id}</p>
                  <p className="text-xs text-gray-500 mt-1">
                    {formatDate(session.created_at)}
                  </p>
                </button>
              </li>
            ))}
          </ul>
          <div className="border-t px-4 py-2 flex items-center justify-between text-xs">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="disabled:opacity-40"
            >
              Previous
            </button>
            <span>
              Page {page} / {totalPages}
            </span>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </section>

        <section className="rounded border bg-white p-4">
          <h2 className="text-sm font-semibold mb-3">Session detail</h2>
          {!detail && (
            <p className="text-sm text-gray-400">Select a session to view messages.</p>
          )}
          {detail && (
            <div className="space-y-4">
              <div className="text-xs text-gray-500 grid grid-cols-2 gap-2">
                <p>
                  <span className="font-medium text-gray-700">Model:</span>{" "}
                  {detail.model_id}
                </p>
                <p>
                  <span className="font-medium text-gray-700">Created:</span>{" "}
                  {formatDate(detail.created_at)}
                </p>
                <p className="col-span-2 truncate">
                  <span className="font-medium text-gray-700">Device:</span>{" "}
                  {detail.device_info || "—"}
                </p>
              </div>

              <div className="space-y-3 max-h-[480px] overflow-y-auto">
                {detail.messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`rounded border p-3 text-sm ${
                      msg.role === "user" ? "bg-blue-50" : "bg-gray-50"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="text-xs font-semibold uppercase text-gray-500">
                        {msg.role}
                      </span>
                      {msg.score && (
                        <DecisionBadge
                          decision={msg.score.decision}
                          composite={msg.score.composite}
                        />
                      )}
                    </div>
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                    {msg.role === "assistant" && (
                      <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px] text-gray-500">
                        <span>TTFT: {msg.ttft_ms} ms</span>
                        <span>tok/s: {msg.tokens_per_sec.toFixed(1)}</span>
                        <span>prompt: {msg.tokens_prompt}</span>
                        <span>completion: {msg.tokens_completion}</span>
                      </div>
                    )}
                    {msg.score && (
                      <div className="mt-2">
                        <ScoreCard score={apiScoreToScoreResult(msg.score)} />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border bg-white p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-lg font-semibold font-mono">{value}</p>
    </div>
  );
}

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded border bg-white">
      <div className="border-b px-4 py-3">
        <h2 className="text-sm font-semibold">{title}</h2>
      </div>
      {children}
    </div>
  );
}

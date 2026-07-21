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
  accept: "#248a3d",
  review: "#b45309",
  reject: "#c41e1e",
};

const CHART_AXIS = "#001D39";
const CHART_GRID = "rgba(73, 118, 159, 0.35)";
const CHART_LINE = "#0A4174";
const CHART_FILL = "#7BBDE8";
const TOOLTIP_STYLE = {
  backgroundColor: "rgba(255, 255, 255, 0.92)",
  backdropFilter: "blur(12px)",
  border: "1px solid rgba(255, 255, 255, 0.5)",
  borderRadius: "12px",
  boxShadow: "0 8px 32px rgba(0, 29, 57, 0.12)",
  color: "#001D39",
  fontSize: "13px",
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
    return <p className="text-[15px] text-ink-muted">Loading dashboard…</p>;
  }

  if (error) {
    return <p className="text-[15px] font-medium text-red-700">{error}</p>;
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">
          Session history, metrics, and decision scoring summaries
        </p>
      </div>

      {metrics && (
        <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
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

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard title="Avg tokens/sec by session">
          {throughputSeries.length === 0 ? (
            <p className="text-[15px] text-ink-muted p-5">No session data yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={throughputSeries}>
                <CartesianGrid stroke={CHART_GRID} strokeDasharray="3 3" />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: CHART_AXIS }} />
                <YAxis tick={{ fontSize: 11, fill: CHART_AXIS }} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Line
                  type="monotone"
                  dataKey="avgTokensPerSec"
                  stroke={CHART_LINE}
                  strokeWidth={2}
                  dot={{ r: 3, fill: CHART_LINE }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Decision distribution">
          {decisionChartData.every((d) => d.count === 0) ? (
            <p className="text-[15px] text-ink-muted p-5">No scores yet.</p>
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
                    label={{ fill: CHART_AXIS, fontSize: 11 }}
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
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                </PieChart>
              </ResponsiveContainer>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={decisionChartData}>
                  <CartesianGrid stroke={CHART_GRID} strokeDasharray="3 3" />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: CHART_AXIS }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: CHART_AXIS }} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Bar dataKey="count" fill={CHART_FILL} radius={[6, 6, 0, 0]}>
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
            <p className="text-[13px] text-ink-muted px-5 pb-4">
              Avg composite score: {scores.avg_composite}
            </p>
          )}
        </ChartCard>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">
        <section className="glass-card-static overflow-hidden p-0">
          <div className="px-5 py-4 border-b border-white/35">
            <h2 className="text-[17px] font-semibold text-ink">Sessions</h2>
          </div>
          <ul className="divide-y divide-white/30 max-h-[420px] overflow-y-auto">
            {sessions.length === 0 && (
              <li className="p-5 text-[15px] text-ink-muted">No sessions yet.</li>
            )}
            {sessions.map((session) => (
              <li key={session.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(session.id)}
                  className={`session-item-hover w-full text-left px-5 py-3.5 text-[15px] transition-colors ${
                    selectedId === session.id ? "session-item-selected" : ""
                  }`}
                >
                  <p className="font-semibold text-ink truncate">{session.model_id}</p>
                  <p className="text-[13px] text-ink-muted mt-0.5">
                    {formatDate(session.created_at)}
                  </p>
                </button>
              </li>
            ))}
          </ul>
          <div className="border-t border-white/35 px-5 py-3 flex items-center justify-between text-[13px] text-ink-muted">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="btn-secondary px-3 py-1.5 text-[13px] disabled:opacity-40"
            >
              Previous
            </button>
            <span className="font-medium text-ink">
              Page {page} / {totalPages}
            </span>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="btn-secondary px-3 py-1.5 text-[13px] disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </section>

        <section className="glass-card-static p-5">
          <h2 className="text-[17px] font-semibold text-ink mb-4">Session detail</h2>
          {!detail && (
            <p className="text-[15px] text-ink-muted">Select a session to view messages.</p>
          )}
          {detail && (
            <div className="space-y-5">
              <div className="text-[13px] text-ink-muted grid grid-cols-2 gap-2">
                <p>
                  <span className="font-medium text-ink">Model:</span>{" "}
                  {detail.model_id}
                </p>
                <p>
                  <span className="font-medium text-ink">Created:</span>{" "}
                  {formatDate(detail.created_at)}
                </p>
                <p className="col-span-2 truncate">
                  <span className="font-medium text-ink">Device:</span>{" "}
                  {detail.device_info || "—"}
                </p>
              </div>

              <div className="space-y-3 max-h-[480px] overflow-y-auto">
                {detail.messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`rounded-[18px] p-4 text-[15px] ${
                      msg.role === "user"
                        ? "bg-sky/25 border border-white/40"
                        : "bg-white/40 border border-white/45 backdrop-blur-sm"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
                        {msg.role}
                      </span>
                      {msg.score && (
                        <DecisionBadge
                          decision={msg.score.decision}
                          composite={msg.score.composite}
                        />
                      )}
                    </div>
                    <p className="whitespace-pre-wrap text-ink">{msg.content}</p>
                    {msg.role === "assistant" && (
                      <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] text-ink-muted">
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
    <div className="glass-card p-5">
      <p className="stat-value">{value}</p>
      <p className="stat-label">{label}</p>
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
    <div className="glass-card-static overflow-hidden p-0">
      <div className="px-5 py-4 border-b border-white/35">
        <h2 className="text-[17px] font-semibold text-ink">{title}</h2>
      </div>
      {children}
    </div>
  );
}

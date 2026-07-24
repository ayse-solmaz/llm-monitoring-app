"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import {
  persistAssistantResult,
  persistSession,
  persistUserMessage,
} from "@/lib/llm-api";
import {
  checkMlcServerHealth,
  fetchCompletion,
  MLC_BASE_URL,
  MLC_MODEL_ID,
} from "@/lib/mlc-server";
import { scoreResponse } from "@/lib/scoring";
import type { LiveMetrics, ModelInfo, ModelsData } from "@/lib/types";
import { useChatStore } from "@/store/chatStore";
import ScoreCard from "@/components/chat/ScoreCard";
import GlowShell from "@/components/ui/GlowShell";

function newId(): string {
  return crypto.randomUUID();
}

function MetricRow({
  label,
  value,
}: {
  label: string;
  value: string | number | null;
}) {
  return (
    <div className="flex justify-between gap-2">
      <span className="metric-label">{label}</span>
      <span className="metric-value text-right">{value ?? "—"}</span>
    </div>
  );
}

function MetricsPanel({ metrics }: { metrics: LiveMetrics }) {
  return (
    <GlowShell variant="card" className="p-5 flex flex-col gap-4 h-fit">
      <div className="relative z-10 flex flex-col gap-4">
        <h2 className="text-[13px] font-semibold uppercase tracking-wide text-ink-muted">
          Live metrics
        </h2>
        <MetricRow
          label="TTFT"
          value={
            metrics.ttftMs !== null ? `${Math.round(metrics.ttftMs)} ms` : null
          }
        />
        <MetricRow
          label="Tokens/sec"
          value={
            metrics.tokensPerSec !== null
              ? metrics.tokensPerSec.toFixed(1)
              : null
          }
        />
        <MetricRow label="Prompt tokens" value={metrics.promptTokens} />
        <MetricRow label="Completion tokens" value={metrics.completionTokens} />
        <MetricRow
          label="Elapsed"
          value={
            metrics.elapsedMs > 0 ? `${Math.round(metrics.elapsedMs)} ms` : null
          }
        />
        {metrics.modelLoadMs !== null && (
          <MetricRow
            label="Connect"
            value={`${Math.round(metrics.modelLoadMs)} ms`}
          />
        )}
        {metrics.isStreaming && (
          <p className="text-[13px] font-medium text-navy-mid animate-pulse">
            Streaming…
          </p>
        )}
      </div>
    </GlowShell>
  );
}

export default function ChatInferenceView() {
  const [serverOk, setServerOk] = useState<boolean | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);

  const {
    selectedModelId,
    modelLoadMs,
    isModelLoading,
    isModelReady,
    loadError,
    messages,
    liveMetrics,
    setSelectedModelId,
    setModelLoading,
    setModelReady,
    setLoadError,
    setModelLoadMs,
    setBackendSessionId,
    addMessage,
    updateMessage,
    setLiveMetrics,
    resetLiveMetrics,
    clearChat,
  } = useChatStore();

  // Health-check server MLC (nginx → replicas)
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    const probe = async () => {
      const ok = await checkMlcServerHealth();
      if (!cancelled) setServerOk(ok);
    };

    void probe();
    timer = setInterval(() => void probe(), 15000);

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const data = await apiFetch<ModelsData>("/config/models");
        if (cancelled) return;
        // Prefer server model id; keep list for UI parity with backend config
        const preferred =
          data.models.find((m) => m.id.includes("gemma-2b")) ?? data.models[0];
        setModels(
          preferred
            ? [
                {
                  ...preferred,
                  id: MLC_MODEL_ID,
                  recommended_device: "cpu (Docker MLC)",
                },
              ]
            : [
                {
                  id: MLC_MODEL_ID,
                  size: "q4f16_1",
                  recommended_device: "cpu (Docker MLC)",
                },
              ]
        );
        setSelectedModelId(MLC_MODEL_ID);
      } catch (err) {
        if (!cancelled) {
          setModels([
            {
              id: MLC_MODEL_ID,
              size: "q4f16_1",
              recommended_device: "cpu (Docker MLC)",
            },
          ]);
          setSelectedModelId(MLC_MODEL_ID);
          setModelsError(
            err instanceof Error
              ? `${err.message} (using ${MLC_MODEL_ID} anyway)`
              : "Using default server model"
          );
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [setSelectedModelId]);

  const connectServer = useCallback(async () => {
    setLoadError(null);
    setModelLoading(true);
    setModelReady(false);
    setModelLoadMs(null);
    setBackendSessionId(null);

    const loadStart = performance.now();

    try {
      const ok = await checkMlcServerHealth(10000);
      if (!ok) {
        throw new Error(
          `Server MLC unavailable at ${MLC_BASE_URL} — run: docker compose up -d --scale mlc=3`
        );
      }
      const loadMs = performance.now() - loadStart;
      setModelLoadMs(loadMs);
      setModelReady(true);
      setServerOk(true);
      setLiveMetrics({ modelLoadMs: loadMs });
      persistSession(MLC_MODEL_ID, loadMs, setBackendSessionId);
    } catch (err) {
      setServerOk(false);
      setLoadError(err instanceof Error ? err.message : String(err));
    } finally {
      setModelLoading(false);
    }
  }, [
    setBackendSessionId,
    setLoadError,
    setLiveMetrics,
    setModelLoadMs,
    setModelLoading,
    setModelReady,
  ]);

  const sendMessage = useCallback(async () => {
    const trimmed = input.trim();
    if (!isModelReady || !trimmed || isStreaming) return;

    setInput("");
    setIsStreaming(true);
    resetLiveMetrics();
    setLiveMetrics({ isStreaming: true, modelLoadMs });

    const priorMessages = useChatStore.getState().messages;
    const apiHistory = priorMessages.map((m) => ({
      role: m.role as "user" | "assistant",
      content: m.content,
    }));

    const userMessage = { id: newId(), role: "user" as const, content: trimmed };
    addMessage(userMessage);

    const sessionId = useChatStore.getState().backendSessionId;
    if (sessionId) {
      persistUserMessage(sessionId, trimmed);
    }

    const assistantId = newId();
    addMessage({ id: assistantId, role: "assistant", content: "" });

    const promptText = [...apiHistory, { role: "user" as const, content: trimmed }]
      .filter((m) => m.role === "user")
      .map((m) => m.content)
      .join("\n");

    let tickTimer: ReturnType<typeof setInterval> | null = null;
    const streamStart = performance.now();
    let livePrompt = 0;
    let liveCompletion = 0;
    let liveTtft: number | null = null;

    tickTimer = setInterval(() => {
      setLiveMetrics({
        ttftMs: liveTtft,
        promptTokens: livePrompt || null,
        completionTokens: liveCompletion || null,
        elapsedMs: performance.now() - streamStart,
        isStreaming: true,
        modelLoadMs,
        tokensPerSec:
          liveCompletion > 0 && liveTtft !== null
            ? liveCompletion /
              Math.max((performance.now() - streamStart - liveTtft) / 1000, 0.001)
            : null,
      });
    }, 100);

    try {
      const result = await fetchCompletion(
        [...apiHistory, { role: "user", content: trimmed }],
        {
          onToken: (_delta, full) => {
            if (liveTtft === null) {
              liveTtft = performance.now() - streamStart;
            }
            updateMessage(assistantId, { content: full });
          },
          onUsage: (p, c) => {
            livePrompt = p;
            liveCompletion = c;
          },
        },
        64
      );

      liveTtft = result.ttftMs;
      livePrompt = result.promptTokens;
      liveCompletion = result.completionTokens;

      const wasTruncated =
        result.content.length > 0 &&
        !/[.!?…]$/.test(result.content.trim());

      const score = scoreResponse({
        ttftMs: result.ttftMs,
        tokensPerSec: result.tokensPerSec,
        promptTokens: result.promptTokens,
        completionTokens: result.completionTokens,
        promptText,
        completionText: result.content,
        wasTruncated,
      });

      const metrics = {
        ttftMs: result.ttftMs,
        tokensPerSec: result.tokensPerSec,
        promptTokens: result.promptTokens,
        completionTokens: result.completionTokens,
        totalMs: result.totalMs,
        modelLoadMs,
        runtimeStatsText: `server MLC @ ${MLC_BASE_URL} (${MLC_MODEL_ID})`,
      };

      updateMessage(assistantId, {
        content: result.content,
        metrics,
        score,
      });
      setLiveMetrics({
        ttftMs: result.ttftMs,
        tokensPerSec: result.tokensPerSec,
        promptTokens: result.promptTokens,
        completionTokens: result.completionTokens,
        elapsedMs: result.totalMs,
        modelLoadMs,
        runtimeStatsText: metrics.runtimeStatsText,
        isStreaming: false,
      });

      const activeSessionId = useChatStore.getState().backendSessionId;
      if (activeSessionId && result.content && !result.content.startsWith("Error:")) {
        persistAssistantResult(
          activeSessionId,
          result.content,
          {
            ttftMs: result.ttftMs,
            tokensPerSec: result.tokensPerSec,
            promptTokens: result.promptTokens,
            completionTokens: result.completionTokens,
            totalMs: result.totalMs,
          },
          score
        );
      }
    } catch (err) {
      const errorText =
        err instanceof Error ? err.message : "Streaming failed";
      updateMessage(assistantId, {
        content: `Error: ${errorText}`,
      });
      setLiveMetrics({ isStreaming: false });
    } finally {
      if (tickTimer) clearInterval(tickTimer);
      setIsStreaming(false);
    }
  }, [
    input,
    isModelReady,
    isStreaming,
    addMessage,
    updateMessage,
    resetLiveMetrics,
    setLiveMetrics,
    modelLoadMs,
  ]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="page-title">Chat</h1>
        <p className="page-subtitle">
          Server-side MLC (Docker CPU) via nginx — live metrics and decision
          scoring. Browser WebLLM demo:{" "}
          <a href="/spike" className="underline text-navy-mid">
            /spike
          </a>
        </p>
      </div>

      <section className="glass-card-static p-5 flex flex-col gap-4">
        <h2 className="text-[17px] font-semibold text-ink">Server MLC</h2>

        {serverOk === null && (
          <p className="text-[15px] text-ink-muted">
            Checking {MLC_BASE_URL}…
          </p>
        )}
        {serverOk === true && (
          <p className="text-[15px] font-medium text-emerald-700">
            Model ready — {MLC_BASE_URL}
          </p>
        )}
        {serverOk === false && (
          <p className="text-[15px] font-medium text-red-600">
            Server MLC unavailable — check{" "}
            <code className="text-[13px]">docker compose up -d --scale mlc=3</code>
          </p>
        )}

        {modelsError && (
          <p className="text-[13px] text-ink-muted">{modelsError}</p>
        )}

        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1.5 text-[15px]">
            <span className="text-ink-muted">Model</span>
            <select
              className="glass-select min-w-[280px]"
              value={selectedModelId ?? MLC_MODEL_ID}
              onChange={(e) => setSelectedModelId(e.target.value)}
              disabled={isModelLoading || isModelReady || isStreaming}
            >
              {(models.length ? models : [{ id: MLC_MODEL_ID, size: "q4f16_1", recommended_device: "cpu" }]).map(
                (m) => (
                  <option key={m.id} value={m.id}>
                    {m.id} ({m.size}, {m.recommended_device})
                  </option>
                )
              )}
            </select>
          </label>
          <button
            type="button"
            onClick={() => void connectServer()}
            disabled={isModelLoading || isModelReady || isStreaming}
            className="btn-primary"
          >
            {isModelReady
              ? "Connected"
              : isModelLoading
                ? "Connecting…"
                : "Connect to server"}
          </button>
          {isModelReady && (
            <button
              type="button"
              onClick={clearChat}
              disabled={isStreaming}
              className="btn-secondary"
            >
              Clear chat
            </button>
          )}
        </div>

        {loadError && (
          <p className="text-[15px] font-medium text-red-600">
            Connect error: {loadError}
          </p>
        )}
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-6">
        <section className="flex flex-col gap-3 min-h-[420px]">
          <div className="flex-1 glass-card-static flex flex-col overflow-hidden p-0">
            <div className="flex-1 overflow-y-auto p-5 space-y-4 max-h-[480px]">
              {messages.length === 0 && (
                <p className="text-[15px] text-ink-muted">
                  Connect to the Docker MLC server, then send a message.
                </p>
              )}
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={msg.role === "user" ? "text-right" : "text-left"}
                >
                  <div
                    className={`inline-block max-w-[90%] px-4 py-2.5 text-[15px] whitespace-pre-wrap ${
                      msg.role === "user" ? "bubble-user" : "bubble-assistant"
                    }`}
                  >
                    {msg.content || (isStreaming ? "…" : "")}
                  </div>
                  {msg.role === "assistant" && msg.score && (
                    <div className="max-w-[90%]">
                      <ScoreCard score={msg.score} />
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="border-t border-white/35 p-4 flex gap-3">
              <textarea
                className="glass-input flex-1 min-h-[72px] resize-y"
                placeholder={
                  isModelReady ? "Type a message…" : "Connect to server first…"
                }
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={!isModelReady || isStreaming}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void sendMessage();
                  }
                }}
              />
              <button
                type="button"
                onClick={() => void sendMessage()}
                disabled={!isModelReady || isStreaming || !input.trim()}
                className="btn-primary self-end shrink-0"
              >
                {isStreaming ? "Streaming…" : "Send"}
              </button>
            </div>
          </div>
        </section>

        <MetricsPanel metrics={liveMetrics} />
      </div>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CreateMLCEngine,
  prebuiltAppConfig,
  type InitProgressReport,
  type MLCEngine,
} from "@mlc-ai/web-llm";
import { apiFetch } from "@/lib/api";
import {
  persistAssistantResult,
  persistSession,
  persistUserMessage,
} from "@/lib/llm-api";
import { scoreResponse } from "@/lib/scoring";
import { estimateTokens } from "@/lib/tokens";
import type { LiveMetrics, ModelInfo, ModelsData } from "@/lib/types";
import { checkWebGPUSupport, WEBGPU_FALLBACK_MESSAGE } from "@/lib/webgpu";
import { useChatStore } from "@/store/chatStore";
import ScoreCard from "@/components/chat/ScoreCard";
import GlowShell from "@/components/ui/GlowShell";

function newId(): string {
  return crypto.randomUUID();
}

function availableModelIds(): Set<string> {
  return new Set(prebuiltAppConfig.model_list.map((m) => m.model_id));
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
            label="Model load"
            value={`${Math.round(metrics.modelLoadMs)} ms`}
          />
        )}
        {metrics.runtimeStatsText && (
          <div className="mt-1 pt-3 border-t border-white/35">
            <p className="metric-label mb-2">Runtime stats</p>
            <pre className="text-[11px] leading-snug whitespace-pre-wrap font-mono bg-white/40 rounded-xl p-3 max-h-40 overflow-auto text-ink">
              {metrics.runtimeStatsText}
            </pre>
          </div>
        )}
        {metrics.isStreaming && (
          <p className="text-[13px] font-medium text-navy-mid animate-pulse">Streaming…</p>
        )}
      </div>
    </GlowShell>
  );
}

export default function ChatInferenceView() {
  const engineRef = useRef<MLCEngine | null>(null);
  const [webgpuSupported, setWebgpuSupported] = useState<boolean | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);

  const {
    selectedModelId,
    modelLoadMs,
    isModelLoading,
    isModelReady,
    loadProgress,
    loadError,
    messages,
    liveMetrics,
    setSelectedModelId,
    setModelLoading,
    setModelReady,
    setLoadProgress,
    setLoadError,
    setModelLoadMs,
    setBackendSessionId,
    addMessage,
    updateMessage,
    setLiveMetrics,
    resetLiveMetrics,
    clearChat,
  } = useChatStore();

  useEffect(() => {
    let cancelled = false;

    void checkWebGPUSupport().then((supported) => {
      if (!cancelled) setWebgpuSupported(supported);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const data = await apiFetch<ModelsData>("/config/models");
        const ids = availableModelIds();
        const filtered = data.models.filter((m) => ids.has(m.id));
        if (cancelled) return;
        setModels(filtered);
        if (filtered.length > 0 && !selectedModelId) {
          setSelectedModelId(filtered[0].id);
        }
      } catch (err) {
        if (!cancelled) {
          setModelsError(
            err instanceof Error ? err.message : "Failed to load models"
          );
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedModelId, setSelectedModelId]);

  const loadModel = useCallback(async () => {
    if (!selectedModelId) return;

    setLoadError(null);
    setModelLoading(true);
    setModelReady(false);
    setLoadProgress(null);
    setModelLoadMs(null);
    setBackendSessionId(null);
    engineRef.current = null;

    const loadStart = performance.now();

    try {
      const engine = await CreateMLCEngine(selectedModelId, {
        initProgressCallback: (report: InitProgressReport) => {
          setLoadProgress(report);
        },
      });
      engineRef.current = engine;
      const loadMs = performance.now() - loadStart;
      setModelLoadMs(loadMs);
      setModelReady(true);
      setLiveMetrics({ modelLoadMs: loadMs });

      persistSession(selectedModelId, loadMs, setBackendSessionId);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
    } finally {
      setModelLoading(false);
    }
  }, [
    selectedModelId,
    setLoadError,
    setLoadProgress,
    setLiveMetrics,
    setModelLoadMs,
    setModelLoading,
    setModelReady,
    setBackendSessionId,
  ]);

  const sendMessage = useCallback(async () => {
    const engine = engineRef.current;
    const trimmed = input.trim();
    if (!engine || !trimmed || isStreaming) return;

    setInput("");
    setIsStreaming(true);
    resetLiveMetrics();
    setLiveMetrics({ isStreaming: true, modelLoadMs });

    const priorMessages = useChatStore.getState().messages;
    const apiHistory = priorMessages.map((m) => ({
      role: m.role,
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
    const promptTokensEstimate = estimateTokens(
      apiHistory.map((m) => m.content).join("\n") + "\n" + trimmed
    );

    const startTime = performance.now();
    let firstTokenTime: number | null = null;
    let fullReply = "";
    let completionTokens = 0;
    let promptTokens = promptTokensEstimate;
    let tickTimer: ReturnType<typeof setInterval> | null = null;

    const updateLive = () => {
      const elapsedMs = performance.now() - startTime;
      const ttftMs =
        firstTokenTime !== null ? firstTokenTime - startTime : null;
      let tokensPerSec: number | null = null;

      if (firstTokenTime !== null && completionTokens > 0) {
        const decodeSec = (performance.now() - firstTokenTime) / 1000;
        if (decodeSec > 0) {
          tokensPerSec = completionTokens / decodeSec;
        }
      }

      setLiveMetrics({
        ttftMs,
        tokensPerSec,
        promptTokens,
        completionTokens,
        elapsedMs,
        isStreaming: true,
        modelLoadMs,
      });
    };

    tickTimer = setInterval(updateLive, 100);

    try {
      const chunks = await engine.chat.completions.create({
        messages: [...apiHistory, { role: "user", content: trimmed }],
        stream: true,
      });

      for await (const chunk of chunks) {
        const delta = chunk.choices[0]?.delta?.content ?? "";
        if (delta && firstTokenTime === null) {
          firstTokenTime = performance.now();
        }
        if (delta) {
          fullReply += delta;
          completionTokens = estimateTokens(fullReply);
          updateMessage(assistantId, { content: fullReply });
          updateLive();
        }

        if (chunk.usage) {
          if (chunk.usage.prompt_tokens) {
            promptTokens = chunk.usage.prompt_tokens;
          }
          if (chunk.usage.completion_tokens) {
            completionTokens = chunk.usage.completion_tokens;
          }
        }
      }

      const totalMs = performance.now() - startTime;
      const ttftMs =
        firstTokenTime !== null ? firstTokenTime - startTime : totalMs;
      const decodeSec =
        firstTokenTime !== null
          ? (performance.now() - firstTokenTime) / 1000
          : totalMs / 1000;
      const tokensPerSec =
        completionTokens > 0 && decodeSec > 0
          ? completionTokens / decodeSec
          : 0;

      let runtimeStatsText: string | null = null;
      try {
        runtimeStatsText = await engine.runtimeStatsText();
      } catch {
        runtimeStatsText = null;
      }

      const wasTruncated =
        fullReply.length > 0 && !/[.!?…]$/.test(fullReply.trim());

      const score = scoreResponse({
        ttftMs,
        tokensPerSec,
        promptTokens,
        completionTokens,
        promptText,
        completionText: fullReply,
        wasTruncated,
      });

      const metrics = {
        ttftMs,
        tokensPerSec,
        promptTokens,
        completionTokens,
        totalMs,
        modelLoadMs,
        runtimeStatsText,
      };

      updateMessage(assistantId, { content: fullReply, metrics, score });
      setLiveMetrics({
        ttftMs,
        tokensPerSec,
        promptTokens,
        completionTokens,
        elapsedMs: totalMs,
        modelLoadMs,
        runtimeStatsText,
        isStreaming: false,
      });

      const activeSessionId = useChatStore.getState().backendSessionId;
      if (activeSessionId && fullReply && !fullReply.startsWith("Error:")) {
        persistAssistantResult(
          activeSessionId,
          fullReply,
          {
            ttftMs,
            tokensPerSec,
            promptTokens,
            completionTokens,
            totalMs,
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
    isStreaming,
    addMessage,
    updateMessage,
    resetLiveMetrics,
    setLiveMetrics,
    modelLoadMs,
  ]);

  const progressPercent = loadProgress
    ? Math.round(loadProgress.progress * 100)
    : 0;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="page-title">Chat</h1>
        <p className="page-subtitle">
          Browser-side inference with live metrics and decision scoring
        </p>
      </div>

      {webgpuSupported === null && (
        <p className="text-[15px] text-ink-muted">Checking WebGPU support…</p>
      )}

      {webgpuSupported === false && (
        <div className="glass-card-static p-5 text-[15px]">
          <p className="font-semibold text-ink">
            {WEBGPU_FALLBACK_MESSAGE.title}
          </p>
          <p className="mt-2 text-ink-body">{WEBGPU_FALLBACK_MESSAGE.body}</p>
          <ul className="mt-2 list-inside list-disc text-ink-body">
            {WEBGPU_FALLBACK_MESSAGE.browsers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
          <p className="mt-2 text-ink-body">{WEBGPU_FALLBACK_MESSAGE.hint}</p>
        </div>
      )}

      {webgpuSupported && (
        <>
          <section className="glass-card-static p-5 flex flex-col gap-4">
            <h2 className="text-[17px] font-semibold text-ink">Model</h2>
            {modelsError && (
              <p className="text-[15px] font-medium text-red-600">{modelsError}</p>
            )}
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1.5 text-[15px]">
                <span className="text-ink-muted">Model</span>
                <select
                  className="glass-select min-w-[280px]"
                  value={selectedModelId ?? ""}
                  onChange={(e) => setSelectedModelId(e.target.value)}
                  disabled={isModelLoading || isModelReady || isStreaming}
                >
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.id} ({m.size}, {m.recommended_device})
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                onClick={loadModel}
                disabled={
                  !selectedModelId || isModelLoading || isModelReady || isStreaming
                }
                className="btn-primary"
              >
                {isModelReady
                  ? "Model loaded"
                  : isModelLoading
                    ? "Loading…"
                    : "Load model"}
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

            {(isModelLoading || loadProgress) && (
              <div className="flex flex-col gap-2">
                <div className="progress-track">
                  <div className="progress-fill" style={{ width: `${progressPercent}%` }} />
                </div>
                <p className="text-[13px] text-ink-muted">
                  {loadProgress?.text ?? "Starting…"} ({progressPercent}%)
                </p>
              </div>
            )}

            {loadError && (
              <p className="text-[15px] font-medium text-red-600">Load error: {loadError}</p>
            )}
          </section>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-6">
            <section className="flex flex-col gap-3 min-h-[420px]">
              <div className="flex-1 glass-card-static flex flex-col overflow-hidden p-0">
                <div className="flex-1 overflow-y-auto p-5 space-y-4 max-h-[480px]">
                  {messages.length === 0 && (
                    <p className="text-[15px] text-ink-muted">
                      Load a model, then send a message to start a multi-turn
                      session.
                    </p>
                  )}
                  {messages.map((msg) => (
                    <div
                      key={msg.id}
                      className={
                        msg.role === "user" ? "text-right" : "text-left"
                      }
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
                      isModelReady
                        ? "Type a message…"
                        : "Load a model first…"
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
                    disabled={
                      !isModelReady || isStreaming || !input.trim()
                    }
                    className="btn-primary self-end shrink-0"
                  >
                    {isStreaming ? "Streaming…" : "Send"}
                  </button>
                </div>
              </div>
            </section>

            <MetricsPanel metrics={liveMetrics} />
          </div>
        </>
      )}
    </div>
  );
}

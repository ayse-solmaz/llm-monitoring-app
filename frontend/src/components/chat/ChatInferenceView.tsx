"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CreateMLCEngine,
  prebuiltAppConfig,
  type InitProgressReport,
  type MLCEngine,
} from "@mlc-ai/web-llm";
import { apiFetch } from "@/lib/api";
import { scoreResponse } from "@/lib/scoring";
import { estimateTokens } from "@/lib/tokens";
import type { LiveMetrics, ModelInfo, ModelsData } from "@/lib/types";
import { checkWebGPUSupport, WEBGPU_FALLBACK_MESSAGE } from "@/lib/webgpu";
import { useChatStore } from "@/store/chatStore";
import ScoreCard from "@/components/chat/ScoreCard";

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
    <div className="flex justify-between gap-2 text-sm">
      <span className="text-gray-500">{label}</span>
      <span className="font-mono text-right">{value ?? "—"}</span>
    </div>
  );
}

function MetricsPanel({ metrics }: { metrics: LiveMetrics }) {
  return (
    <aside className="rounded border bg-gray-50 p-4 flex flex-col gap-3 h-fit">
      <h2 className="text-sm font-semibold">Live metrics</h2>
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
        <div className="mt-1">
          <p className="text-xs text-gray-500 mb-1">Runtime stats</p>
          <pre className="text-[10px] leading-snug whitespace-pre-wrap font-mono bg-white border rounded p-2 max-h-40 overflow-auto">
            {metrics.runtimeStatsText}
          </pre>
        </div>
      )}
      {metrics.isStreaming && (
        <p className="text-xs text-blue-600 animate-pulse">Streaming…</p>
      )}
    </aside>
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
    <div className="max-w-6xl mx-auto flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold">Chat</h1>
        <p className="text-sm text-gray-600">
          Browser-side inference with live metrics and decision scoring
        </p>
      </div>

      {webgpuSupported === null && (
        <p className="text-sm text-gray-500">Checking WebGPU support…</p>
      )}

      {webgpuSupported === false && (
        <div className="rounded border border-amber-300 bg-amber-50 p-4 text-sm">
          <p className="font-medium text-amber-900">
            {WEBGPU_FALLBACK_MESSAGE.title}
          </p>
          <p className="mt-2 text-amber-800">{WEBGPU_FALLBACK_MESSAGE.body}</p>
          <ul className="mt-2 list-inside list-disc text-amber-800">
            {WEBGPU_FALLBACK_MESSAGE.browsers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
          <p className="mt-2 text-amber-800">{WEBGPU_FALLBACK_MESSAGE.hint}</p>
        </div>
      )}

      {webgpuSupported && (
        <>
          {/* Subview 2a — model selector + load */}
          <section className="rounded border p-4 flex flex-col gap-3">
            <h2 className="text-sm font-semibold">Model</h2>
            {modelsError && (
              <p className="text-sm text-red-600">{modelsError}</p>
            )}
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-gray-600">Model</span>
                <select
                  className="border rounded px-3 py-2 min-w-[280px] text-sm"
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
                className="rounded border px-4 py-2 text-sm disabled:opacity-50"
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
                  className="rounded border px-3 py-2 text-sm text-gray-600 disabled:opacity-50"
                >
                  Clear chat
                </button>
              )}
            </div>

            {(isModelLoading || loadProgress) && (
              <div className="flex flex-col gap-1">
                <div className="h-3 w-full overflow-hidden rounded bg-gray-200">
                  <div
                    className="h-full bg-blue-500 transition-all"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
                <p className="text-xs text-gray-600">
                  {loadProgress?.text ?? "Starting…"} ({progressPercent}%)
                </p>
              </div>
            )}

            {loadError && (
              <p className="text-sm text-red-600">Load error: {loadError}</p>
            )}
          </section>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
            {/* Subview 2b — chat */}
            <section className="flex flex-col gap-3 min-h-[420px]">
              <div className="flex-1 rounded border bg-white flex flex-col">
                <div className="flex-1 overflow-y-auto p-4 space-y-4 max-h-[480px]">
                  {messages.length === 0 && (
                    <p className="text-sm text-gray-400">
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
                        className={`inline-block max-w-[90%] rounded px-3 py-2 text-sm whitespace-pre-wrap ${
                          msg.role === "user"
                            ? "bg-blue-600 text-white"
                            : "bg-gray-100 text-gray-900"
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

                <div className="border-t p-3 flex gap-2">
                  <textarea
                    className="flex-1 min-h-[72px] rounded border p-2 text-sm resize-y"
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
                    className="self-end rounded border px-4 py-2 text-sm disabled:opacity-50"
                  >
                    {isStreaming ? "Streaming…" : "Send"}
                  </button>
                </div>
              </div>
            </section>

            {/* Subview 2c — live metrics */}
            <MetricsPanel metrics={liveMetrics} />
          </div>
        </>
      )}
    </div>
  );
}

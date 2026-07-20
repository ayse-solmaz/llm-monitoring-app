"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CreateMLCEngine,
  prebuiltAppConfig,
  type InitProgressReport,
  type MLCEngine,
} from "@mlc-ai/web-llm";

const REQUESTED_MODEL = "gemma-2-2b-it-q4f16_1-MLC";

function resolveModelId(): string {
  const modelIds = prebuiltAppConfig.model_list.map((m) => m.model_id);
  if (modelIds.includes(REQUESTED_MODEL)) {
    return REQUESTED_MODEL;
  }

  const gemmaInstruct = prebuiltAppConfig.model_list.filter(
    (m) =>
      /gemma/i.test(m.model_id) &&
      /it/i.test(m.model_id) &&
      !/jpn/i.test(m.model_id)
  );

  if (gemmaInstruct.length === 0) {
    throw new Error("No Gemma instruct models found in prebuiltAppConfig");
  }

  gemmaInstruct.sort((a, b) => {
    const vramA = a.vram_required_MB ?? Number.MAX_SAFE_INTEGER;
    const vramB = b.vram_required_MB ?? Number.MAX_SAFE_INTEGER;
    if (vramA !== vramB) return vramA - vramB;
    return a.model_id.localeCompare(b.model_id);
  });

  return gemmaInstruct[0].model_id;
}

const MODEL_ID = resolveModelId();

const WEBGPU_ADAPTER_TIMEOUT_MS = 5000;
const WEBGPU_SAFETY_TIMEOUT_MS = 8000;

type NavigatorWithGPU = Navigator & {
  gpu?: { requestAdapter: () => Promise<unknown | null> };
};

function requestAdapterWithTimeout(
  gpu: NonNullable<NavigatorWithGPU["gpu"]>
): Promise<{ adapter: unknown | null; timedOut: boolean }> {
  return new Promise((resolve) => {
    let settled = false;

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      console.log(
        "[WebGPU] requestAdapter timed out after",
        WEBGPU_ADAPTER_TIMEOUT_MS,
        "ms — using presence fallback"
      );
      resolve({ adapter: null, timedOut: true });
    }, WEBGPU_ADAPTER_TIMEOUT_MS);

    gpu
      .requestAdapter()
      .then((adapter) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        console.log(
          "[WebGPU] requestAdapter resolved:",
          adapter ? "adapter OK" : "null adapter"
        );
        resolve({ adapter, timedOut: false });
      })
      .catch((err) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        console.log("[WebGPU] requestAdapter threw:", err);
        resolve({ adapter: null, timedOut: false });
      });
  });
}

async function checkWebGPUSupport(): Promise<boolean> {
  console.log("[WebGPU] step 1: check start");

  if (typeof window === "undefined") {
    console.log("[WebGPU] step 2: no window (SSR) → unsupported");
    return false;
  }

  console.log("[WebGPU] step 2: window OK, inspecting navigator.gpu");
  const gpu = (navigator as NavigatorWithGPU).gpu;

  if (!gpu) {
    console.log("[WebGPU] step 3: navigator.gpu missing → unsupported");
    return false;
  }

  console.log("[WebGPU] step 3: navigator.gpu present");
  console.log("[WebGPU] step 4: calling requestAdapter (with timeout)…");

  const { adapter, timedOut } = await requestAdapterWithTimeout(gpu);

  if (timedOut) {
    console.log(
      "[WebGPU] step 5: adapter timed out → supported (navigator.gpu present)"
    );
    return true;
  }

  const supported = adapter !== null;
  console.log(
    "[WebGPU] step 5: final result →",
    supported ? "supported" : "unsupported"
  );
  return supported;
}

export default function SpikePage() {
  const engineRef = useRef<MLCEngine | null>(null);

  const [webgpuSupported, setWebgpuSupported] = useState<boolean | null>(null);
  const [loadProgress, setLoadProgress] = useState<InitProgressReport | null>(
    null
  );
  const [isLoading, setIsLoading] = useState(false);
  const [isModelReady, setIsModelReady] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [prompt, setPrompt] = useState("");
  const [response, setResponse] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);

  useEffect(() => {
    let cancelled = false;

    console.log("[WebGPU] useEffect: client-side check starting");

    const safetyTimer = setTimeout(() => {
      if (cancelled) return;
      const present = !!(navigator as NavigatorWithGPU).gpu;
      console.warn(
        "[WebGPU] safety timeout fired — forcing state from navigator.gpu presence:",
        present
      );
      setWebgpuSupported(present);
    }, WEBGPU_SAFETY_TIMEOUT_MS);

    void (async () => {
      try {
        const supported = await checkWebGPUSupport();
        if (cancelled) {
          console.log("[WebGPU] check finished but effect was cancelled");
          return;
        }
        clearTimeout(safetyTimer);
        console.log("[WebGPU] setting UI state →", supported ? "supported" : "unsupported");
        setWebgpuSupported(supported);
      } catch (err) {
        if (cancelled) return;
        clearTimeout(safetyTimer);
        console.error("[WebGPU] unexpected error → unsupported:", err);
        setWebgpuSupported(false);
      }
    })();

    return () => {
      cancelled = true;
      clearTimeout(safetyTimer);
      console.log("[WebGPU] useEffect cleanup");
    };
  }, []);

  const loadModel = useCallback(async () => {
    setLoadError(null);
    setIsLoading(true);
    setLoadProgress(null);
    setIsModelReady(false);

    try {
      const engine = await CreateMLCEngine(MODEL_ID, {
        initProgressCallback: (report) => {
          setLoadProgress(report);
        },
      });
      engineRef.current = engine;
      setIsModelReady(true);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const sendPrompt = useCallback(async () => {
    const engine = engineRef.current;
    if (!engine || !prompt.trim() || isStreaming) return;

    setIsStreaming(true);
    setResponse("");

    const startTime = performance.now();
    let firstTokenTime: number | null = null;
    let fullReply = "";

    try {
      const chunks = await engine.chat.completions.create({
        messages: [{ role: "user", content: prompt.trim() }],
        stream: true,
      });

      for await (const chunk of chunks) {
        const delta = chunk.choices[0]?.delta?.content ?? "";
        if (delta && firstTokenTime === null) {
          firstTokenTime = performance.now();
          console.log(
            "Time to first token (ms):",
            Math.round(firstTokenTime - startTime)
          );
        }
        if (delta) {
          fullReply += delta;
          setResponse(fullReply);
        }
      }

      const totalTime = Math.round(performance.now() - startTime);
      console.log("Total time (ms):", totalTime);

      const stats = await engine.runtimeStatsText();
      console.log("Runtime stats:\n", stats);
    } catch (err) {
      console.error("Streaming error:", err);
      setResponse(
        `Error: ${err instanceof Error ? err.message : String(err)}`
      );
    } finally {
      setIsStreaming(false);
    }
  }, [prompt, isStreaming]);

  const progressPercent = loadProgress
    ? Math.round(loadProgress.progress * 100)
    : 0;

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-4 p-6">
      <h1 className="text-xl font-semibold">WebLLM Spike</h1>
      <p className="text-sm text-gray-600">Model: {MODEL_ID}</p>

      {webgpuSupported === null && (
        <p className="text-sm text-gray-500">Checking WebGPU support…</p>
      )}

      {webgpuSupported === false && (
        <div className="rounded border border-amber-300 bg-amber-50 p-4 text-sm">
          <p className="font-medium text-amber-900">WebGPU not supported</p>
          <p className="mt-2 text-amber-800">
            This spike requires WebGPU. Use a recent desktop browser with WebGPU
            enabled:
          </p>
          <ul className="mt-2 list-inside list-disc text-amber-800">
            <li>Google Chrome 113+ (recommended)</li>
            <li>Microsoft Edge 113+</li>
            <li>Other Chromium browsers with WebGPU enabled</li>
          </ul>
          <p className="mt-2 text-amber-800">
            Safari and Firefox may not work yet. Enable GPU in Chrome at{" "}
            <code className="text-xs">chrome://settings/system</code>.
          </p>
        </div>
      )}

      {webgpuSupported && (
        <>
          <div className="flex flex-col gap-2">
            <button
              type="button"
              onClick={loadModel}
              disabled={isLoading || isModelReady}
              className="w-fit rounded border px-4 py-2 text-sm disabled:opacity-50"
            >
              {isModelReady
                ? "Model loaded"
                : isLoading
                  ? "Loading model…"
                  : "Load model"}
            </button>

            {(isLoading || loadProgress) && (
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
          </div>

          <textarea
            className="min-h-28 w-full rounded border p-3 text-sm"
            placeholder="Enter a prompt…"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={!isModelReady || isStreaming}
          />

          <button
            type="button"
            onClick={sendPrompt}
            disabled={!isModelReady || isStreaming || !prompt.trim()}
            className="w-fit rounded border px-4 py-2 text-sm disabled:opacity-50"
          >
            {isStreaming ? "Streaming…" : "Send"}
          </button>

          {response && (
            <div className="rounded border bg-gray-50 p-3 text-sm whitespace-pre-wrap">
              {response}
            </div>
          )}
        </>
      )}
    </main>
  );
}

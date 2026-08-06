"use client";

import { useCallback, useEffect, useState } from "react";
import {
  fetchGatewayMetrics,
  type GatewayMetricSnapshot,
} from "@/lib/gateway-metrics";
import { useLlmAdminStore } from "@/store/llmAdminStore";

/** Known adapter ids (folders under peft-adapters/). Soft hot-swap on next Chat send. */
const ADAPTERS = [
  { id: "", label: "Base model (no LoRA)" },
  { id: "deepkwiki", label: "deepkwiki — docs / wiki tone" },
  { id: "code-assistant", label: "code-assistant — concise code help" },
];

export default function AdminLlmPanel() {
  const {
    systemPrompt,
    temperature,
    topP,
    maxTokens,
    adapterId,
    deepKwikiEnabled,
    dirty,
    saving,
    lastSavedAt,
    syncError,
    setSystemPrompt,
    setTemperature,
    setTopP,
    setMaxTokens,
    setAdapterId,
    setDeepKwikiEnabled,
    saveToApi,
    resetDefaults,
  } = useLlmAdminStore();

  const [metrics, setMetrics] = useState<GatewayMetricSnapshot | null>(null);
  const [saveOk, setSaveOk] = useState<string | null>(null);

  const refreshMetrics = useCallback(async () => {
    setMetrics(await fetchGatewayMetrics());
  }, []);

  useEffect(() => {
    void refreshMetrics();
    const t = setInterval(() => void refreshMetrics(), 10000);
    return () => clearInterval(t);
  }, [refreshMetrics]);

  async function handleSave() {
    setSaveOk(null);
    try {
      await saveToApi();
      setSaveOk("Settings saved — apply on next Chat message.");
    } catch {
      // syncError is set in store
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="page-title">Admin — LLM controls</h1>
        <p className="page-subtitle">
          FINAL BOSS soft hot-swap: adapter / prompt / sampling apply on the{" "}
          <strong>next Chat message</strong> (no container restart). Settings
          persist in the backend; DeepKwiki injects project facts when enabled.
        </p>
        {(dirty || syncError || saveOk || lastSavedAt) && (
          <p className="text-[14px] mt-2">
            {dirty && !saving && (
              <span className="text-amber-700">Unsaved changes · </span>
            )}
            {saving && <span className="text-ink-muted">Saving… · </span>}
            {saveOk && <span className="text-green-800">{saveOk} · </span>}
            {syncError && (
              <span className="text-red-700">Sync: {syncError} · </span>
            )}
            {lastSavedAt && !dirty && (
              <span className="text-ink-muted">Last saved {lastSavedAt}</span>
            )}
          </p>
        )}
      </div>

      <section className="glass-card-static p-5 flex flex-col gap-4">
        <h2 className="text-[17px] font-semibold text-ink">Adapter management</h2>
        <p className="text-[14px] text-ink-muted">
          Soft hot-swap: selected id changes prompt style immediately. Real LoRA
          weight load needs GPU MLC serve (see docker-compose.gpu.yml).
        </p>
        <label className="flex flex-col gap-1.5 text-[15px]">
          <span className="text-ink-muted">Active adapter</span>
          <select
            className="glass-select max-w-md"
            value={adapterId}
            onChange={(e) => setAdapterId(e.target.value)}
          >
            {ADAPTERS.map((a) => (
              <option key={a.id || "base"} value={a.id}>
                {a.label}
              </option>
            ))}
          </select>
        </label>
        <p className="text-[14px] text-ink-muted">
          Tip: DeepKwiki is on by default for factual project Qs. CPU Gemma —
          max tokens ≤48, one message at a time. Reset if old browser settings
          look wrong.
        </p>
      </section>

      <section className="glass-card-static p-5 flex flex-col gap-4">
        <h2 className="text-[17px] font-semibold text-ink">System prompt</h2>
        <textarea
          className="glass-input min-h-[120px] resize-y font-mono text-[14px]"
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
        />
        <label className="flex items-center gap-2 text-[15px]">
          <input
            type="checkbox"
            checked={deepKwikiEnabled}
            onChange={(e) => setDeepKwikiEnabled(e.target.checked)}
          />
          <span>Enable DeepKwiki context injection</span>
        </label>
      </section>

      <section className="glass-card-static p-5 flex flex-col gap-5">
        <h2 className="text-[17px] font-semibold text-ink">
          Context limits & sampling
        </h2>
        <label className="flex flex-col gap-1.5 text-[15px] max-w-xs">
          <span className="text-ink-muted">
            Temperature: {temperature.toFixed(2)}
          </span>
          <input
            type="range"
            min={0}
            max={1.5}
            step={0.05}
            value={temperature}
            onChange={(e) => setTemperature(Number(e.target.value))}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-[15px] max-w-xs">
          <span className="text-ink-muted">Top-P: {topP.toFixed(2)}</span>
          <input
            type="range"
            min={0.1}
            max={1}
            step={0.05}
            value={topP}
            onChange={(e) => setTopP(Number(e.target.value))}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-[15px] max-w-xs">
          <span className="text-ink-muted">Max tokens</span>
          <input
            type="number"
            className="glass-input"
            min={8}
            max={512}
            value={maxTokens}
            onChange={(e) =>
              setMaxTokens(
                Math.min(512, Math.max(8, Number(e.target.value) || 256))
              )
            }
          />
        </label>
      </section>

      <section className="glass-card-static p-5 flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[17px] font-semibold text-ink">Log monitor</h2>
          <button
            type="button"
            className="btn-secondary text-[13px]"
            onClick={() => void refreshMetrics()}
          >
            Refresh
          </button>
        </div>
        {metrics?.ok ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[14px]">
            <div>
              <div className="text-ink-muted">Requests</div>
              <div className="font-semibold text-ink">{metrics.requestsTotal}</div>
            </div>
            <div>
              <div className="text-ink-muted">Errors</div>
              <div className="font-semibold text-ink">{metrics.requestsError}</div>
            </div>
            <div>
              <div className="text-ink-muted">Inflight</div>
              <div className="font-semibold text-ink">{metrics.inflight}</div>
            </div>
            <div>
              <div className="text-ink-muted">Out tokens</div>
              <div className="font-semibold text-ink">{metrics.outputTokens}</div>
            </div>
          </div>
        ) : (
          <p className="text-[14px] text-ink-muted">
            Gateway metrics unavailable
            {metrics?.error ? `: ${metrics.error}` : ""}. Start stack:{" "}
            <code className="text-[13px]">
              docker compose up -d --scale mlc=1
            </code>
          </p>
        )}
        <p className="text-[13px] text-ink-muted">
          Grafana{" "}
          <a
            href="http://localhost:3000"
            className="underline text-navy-mid"
            target="_blank"
            rel="noreferrer"
          >
            :3000
          </a>{" "}
          (admin/admin) · raw{" "}
          <a
            href="http://localhost:8080/metrics"
            className="underline text-navy-mid"
            target="_blank"
            rel="noreferrer"
          >
            :8080/metrics
          </a>
          {metrics?.scrapedAt ? ` · scraped ${metrics.scrapedAt}` : ""}
        </p>
      </section>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          className="btn-primary"
          disabled={saving || !dirty}
          onClick={() => void handleSave()}
        >
          {saving ? "Saving…" : "Save settings"}
        </button>
        <button type="button" className="btn-secondary" onClick={resetDefaults}>
          Reset to defaults
        </button>
      </div>
    </div>
  );
}

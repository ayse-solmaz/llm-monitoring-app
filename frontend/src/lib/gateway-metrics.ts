/**
 * Parse Prometheus text exposition from mlc-gateway /metrics (FINAL BOSS Admin log).
 */

export type GatewayMetricSnapshot = {
  ok: boolean;
  error?: string;
  requestsTotal: number;
  requestsError: number;
  inflight: number;
  outputTokens: number;
  scrapedAt: string;
};

export async function fetchGatewayMetrics(
  baseUrl = "/api/mlc"
): Promise<GatewayMetricSnapshot> {
  const scrapedAt = new Date().toISOString();
  try {
    const res = await fetch(`${baseUrl}/metrics`, { cache: "no-store" });
    if (!res.ok) {
      return {
        ok: false,
        error: `HTTP ${res.status}`,
        requestsTotal: 0,
        requestsError: 0,
        inflight: 0,
        outputTokens: 0,
        scrapedAt,
      };
    }
    const text = await res.text();
    let requestsTotal = 0;
    let requestsError = 0;
    let inflight = 0;
    let outputTokens = 0;

    for (const raw of text.split("\n")) {
      const line = raw.trim();
      if (!line || line.startsWith("#")) continue;
      const sp = line.lastIndexOf(" ");
      if (sp < 0) continue;
      const namePart = line.slice(0, sp);
      const val = Number(line.slice(sp + 1)) || 0;
      const metric = namePart.split("{")[0];

      if (metric === "llm_requests_total") {
        requestsTotal += val;
        if (namePart.includes('status="error"')) requestsError += val;
      } else if (metric === "llm_requests_inflight") {
        inflight = val;
      } else if (metric === "llm_output_tokens_total") {
        outputTokens += val;
      }
    }

    return {
      ok: true,
      requestsTotal,
      requestsError,
      inflight,
      outputTokens,
      scrapedAt,
    };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : "fetch failed",
      requestsTotal: 0,
      requestsError: 0,
      inflight: 0,
      outputTokens: 0,
      scrapedAt,
    };
  }
}

/**
 * DeepKwiki — static knowledge snippets injected into chat context (FINAL BOSS).
 * No external search API; local corpus for demo / offline use.
 */

export type WikiHit = {
  id: string;
  title: string;
  body: string;
  tags: string[];
};

const CORPUS: WikiHit[] = [
  {
    id: "mlc-docker",
    title: "MLC-LLM in Docker",
    tags: ["mlc", "docker", "cpu", "gpu"],
    body: "This project runs Gemma 2B via MLC-LLM in Docker (CPU spike image mlc-server-spike). Public entry is the FastAPI KPI gateway on :8080, which load-balances through nginx least_conn to scaled mlc replicas sharing a named volume for weights.",
  },
  {
    id: "kpi-gateway",
    title: "KPI Gateway",
    tags: ["kpi", "prometheus", "ttft", "gateway"],
    body: "The mlc-gateway service proxies /v1/chat/completions with stream=true, records TTFT, E2E latency, tokens/sec, inflight requests, and exposes Prometheus metrics at /metrics. Grafana scrapes via Prometheus (pull model).",
  },
  {
    id: "scaling",
    title: "Horizontal scaling",
    tags: ["scale", "replica", "nginx", "hpa"],
    body: "Local demo uses docker compose --scale mlc=N. Same image, shared mlc-model volume (read-only). Cloud equivalent is Kubernetes HPA/KEDA scaling pods on CPU or custom queue metrics. Multi-replica on one CPU/GPU mostly buys concurrency, not linear speedup.",
  },
  {
    id: "peft",
    title: "PEFT / LoRA adapters",
    tags: ["peft", "lora", "qlora", "adapter"],
    body: "PEFT (LoRA/QLoRA) adds small adapter weights instead of full fine-tunes. Adapters are expected under peft-adapters/ and mounted into MLC containers. Hot-swap of adapters without restart is the Admin panel target; CPU demo may only pass adapter id as metadata until GPU LoRA serve is wired.",
  },
  {
    id: "auth",
    title: "Auth & monitoring API",
    tags: ["jwt", "render", "session", "score"],
    body: "Go backend (masterfabric-go) on Render handles JWT auth and persists sessions, messages, and decision scores. Frontend chat can call local MLC while saving metrics to the cloud API via NEXT_PUBLIC_API_URL.",
  },
  {
    id: "final-boss",
    title: "FINAL BOSS architecture",
    tags: ["final", "boss", "mcp", "admin", "webmcp"],
    body: "FINAL BOSS combines local Docker MLC, frontend WebMCP (DeepKwiki packaging), Go internal MCP HandleMCPRequest (no new PRD routes), Admin soft hot-swap for adapters/prompts/sampling, and Rich Result Markdown in Chat.",
  },
];

/** Simple keyword overlap search — returns top matches for prompt enrichment. */
export function searchDeepKwiki(query: string, limit = 1): WikiHit[] {
  const q = query.toLowerCase().trim();
  if (!q) return [];

  const terms = q.split(/\s+/).filter((t) => t.length > 2);
  if (terms.length === 0) return [];

  const scored = CORPUS.map((hit) => {
    const hay = `${hit.title} ${hit.body} ${hit.tags.join(" ")}`.toLowerCase();
    let score = 0;
    for (const t of terms) {
      if (hay.includes(t)) score += 1;
      if (hit.tags.includes(t)) score += 2;
    }
    return { hit, score };
  })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score);

  // No match → no injection (forcing unrelated wiki confused Gemma).
  return scored.slice(0, limit).map((x) => x.hit);
}

/** Build a short context block from wiki hits. */
export function formatWikiContext(hits: WikiHit[]): string {
  if (hits.length === 0) return "";
  const blocks = hits.map((h) => `${h.title}: ${h.body}`);
  return `Project facts (use only if relevant):\n${blocks.join("\n")}`;
}

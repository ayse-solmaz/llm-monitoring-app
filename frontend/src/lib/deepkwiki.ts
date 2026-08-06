/**
 * DeepKwiki — static knowledge snippets injected into chat context (FINAL BOSS).
 * Problem B fix: verified project facts via prompt injection (no retrain / no weight edits).
 */

export type WikiHit = {
  id: string;
  title: string;
  body: string;
  tags: string[];
};

/**
 * Compact, verified answers for factual gaps + stack reference.
 * Keep bodies short — Gemma CPU prompts are truncated in webmcp.
 */
const PROJECT_FACTS: WikiHit[] = [
  {
    id: "physics-water-boil",
    title: "Su kaynama sıcaklığı",
    tags: ["su", "kaynama", "kaynar", "derece", "100", "fizik", "celsius", "kaynama"],
    body: "Deniz seviyesinde su 100 derecede (100°C) kaynar.",
  },
  {
    id: "backend-stack",
    title: "Backend dili ve stack",
    tags: ["backend", "go", "golang", "api", "dil", "gin", "gorm", "postgres"],
    body: "Bu projenin backend'i Go (Golang) ile yazılmıştır: Gin, GORM, PostgreSQL.",
  },
  {
    id: "jwt-tokens",
    title: "JWT access ve refresh süreleri",
    tags: ["jwt", "access", "token", "refresh", "dakika", "auth", "geçerlilik", "süre"],
    body: "Access token 15 dakika geçerlidir. Refresh token 7 gün geçerlidir.",
  },
  {
    id: "ports",
    title: "Yerel portlar",
    tags: ["port", "8080", "3002", "3000", "9090", "gateway"],
    body: "MLC KPI gateway :8080, frontend dev :3002, Grafana :3000, Prometheus :9090.",
  },
  {
    id: "model-prod",
    title: "Prod model",
    tags: ["model", "gemma", "q4f16_2", "mlc", "finetune", "quant"],
    body: "Prod'da fine-tuned Gemma 2B-IT, MLC q4f16_2 (embed/lm_head float) Docker CPU'da servis edilir.",
  },
  {
    id: "architecture",
    title: "Mimari özet",
    tags: ["mimari", "architecture", "vercel", "render", "docker"],
    body: "Frontend Next.js (Vercel), backend Go (Render), inference MLC-LLM Docker local (:8080 gateway).",
  },
];

const ARCH_SNIPPETS: WikiHit[] = [
  {
    id: "mlc-docker",
    title: "MLC-LLM in Docker",
    tags: ["mlc", "docker", "cpu", "gpu"],
    body: "Gemma 2B MLC-LLM Docker CPU (mlc-server-spike). Giriş FastAPI KPI gateway :8080 → nginx → mlc replicas (shared volume).",
  },
  {
    id: "kpi-gateway",
    title: "KPI Gateway",
    tags: ["kpi", "prometheus", "ttft", "gateway"],
    body: "mlc-gateway proxies /v1/chat/completions (stream), records TTFT/E2E/tok/s, /metrics for Prometheus/Grafana.",
  },
  {
    id: "peft",
    title: "PEFT / LoRA adapters",
    tags: ["peft", "lora", "qlora", "adapter"],
    body: "PEFT LoRA adapters under peft-adapters/. Admin soft-swap passes adapter id as prompt style on CPU demo.",
  },
  {
    id: "auth",
    title: "Auth & monitoring API",
    tags: ["jwt", "render", "session", "score"],
    body: "Go backend JWT auth (access 15 dk, refresh 7 gün); sessions/messages/scores via NEXT_PUBLIC_API_URL.",
  },
];

const CORPUS: WikiHit[] = [...PROJECT_FACTS, ...ARCH_SNIPPETS];

/** High-confidence patterns for Problem B factual gaps. */
const FACT_PATTERNS: Array<{ re: RegExp; id: string }> = [
  {
    re: /su\s+kaç|kaç\s+derece.*kaynar|kaynama|water.*boil/i,
    id: "physics-water-boil",
  },
  {
    re: /backend.*(dil|language)|projenin\s+backend|hangi\s+(dil|language).*backend|backend\s+dili/i,
    id: "backend-stack",
  },
  {
    re: /access\s*token|token\s+kaç\s+dakika|jwt.*(dakika|süre)|refresh\s*token.*geçer/i,
    id: "jwt-tokens",
  },
  { re: /\b(port|8080|grafana|prometheus)\b/i, id: "ports" },
  {
    re: /hangi\s+model|prod.*model|q4f16|quantiz/i,
    id: "model-prod",
  },
];

const SHORT_TERMS = new Set(["su", "go"]);

function matchByPattern(query: string): WikiHit[] {
  const hits: WikiHit[] = [];
  for (const { re, id } of FACT_PATTERNS) {
    if (!re.test(query)) continue;
    const hit = CORPUS.find((h) => h.id === id);
    if (hit && !hits.some((h) => h.id === id)) hits.push(hit);
  }
  return hits;
}

/** Simple keyword overlap search — returns top matches for prompt enrichment. */
export function searchDeepKwiki(query: string, limit = 1): WikiHit[] {
  const q = query.toLowerCase().trim();
  if (!q) return [];

  const patternHits = matchByPattern(q);
  if (patternHits.length > 0) return patternHits.slice(0, limit);

  const terms = q.split(/\s+/).filter((t) => t.length > 2 || SHORT_TERMS.has(t));
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
  return `Project facts — answer from these if they apply:\n${blocks.join("\n")}`;
}

/** Exported for smoke tests / scripts. */
export function listDeepKwikiCorpus(): WikiHit[] {
  return CORPUS.slice();
}

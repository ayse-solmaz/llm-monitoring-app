/**
 * Deterministic decision scoring (PRD §5).
 *
 * Weights: latency 0.4, length 0.3, format 0.3
 * Decision: accept >= 70, review >= 40, else reject
 */

export type Decision = "accept" | "review" | "reject";

export type ScoreInput = {
  ttftMs: number;
  tokensPerSec: number;
  promptTokens: number;
  completionTokens: number;
  promptText: string;
  completionText: string;
  wasTruncated?: boolean;
};

export type ScoreResult = {
  latencyScore: number;
  lengthScore: number;
  formatScore: number;
  composite: number;
  decision: Decision;
};

const WEIGHTS = { latency: 0.4, length: 0.3, format: 0.3 } as const;
const THRESHOLDS = { accept: 70, review: 40 } as const;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function scoreFromThresholds(
  value: number,
  thresholds: Array<{ max: number; score: number }>
): number {
  for (const tier of thresholds) {
    if (value <= tier.max) return tier.score;
  }
  return thresholds[thresholds.length - 1]?.score ?? 0;
}

/**
 * Latency score from TTFT (50%) and decode speed (50%).
 *
 * TTFT thresholds (ms): <=500→100, <=1000→85, <=2000→65, <=5000→40, else 15
 * tok/s thresholds:      >=25→100, >=15→85, >=10→65, >=5→40, else 15
 */
export function latencyScore(
  ttftMs: number,
  tokensPerSec: number
): number {
  const ttft = scoreFromThresholds(ttftMs, [
    { max: 500, score: 100 },
    { max: 1000, score: 85 },
    { max: 2000, score: 65 },
    { max: 5000, score: 40 },
    { max: Infinity, score: 15 },
  ]);

  const throughput = scoreFromThresholds(-tokensPerSec, [
    { max: -25, score: 100 },
    { max: -15, score: 85 },
    { max: -10, score: 65 },
    { max: -5, score: 40 },
    { max: Infinity, score: 15 },
  ]);

  return Math.round((ttft + throughput) / 2);
}

/**
 * Length score from completion/prompt token ratio.
 *
 * Ideal ratio band: 0.5–3.0 → 100
 * Too short (<0.2): 25 | short (<0.5): 60 | long (3–6): 70 | very long (6–12): 45 | else 20
 */
export function lengthScore(
  promptTokens: number,
  completionTokens: number
): number {
  const prompt = Math.max(promptTokens, 1);
  const ratio = completionTokens / prompt;

  if (ratio >= 0.5 && ratio <= 3) return 100;
  if (ratio < 0.2) return 25;
  if (ratio < 0.5) return 60;
  if (ratio <= 6) return 70;
  if (ratio <= 12) return 45;
  return 20;
}

function repetitionRatio(text: string): number {
  const words = text.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length < 8) return 0;

  const grams = new Map<string, number>();
  for (let i = 0; i < words.length - 3; i++) {
    const gram = words.slice(i, i + 4).join(" ");
    grams.set(gram, (grams.get(gram) ?? 0) + 1);
  }

  let repeated = 0;
  for (const count of Array.from(grams.values())) {
    if (count > 1) repeated += count - 1;
  }

  return repeated / Math.max(words.length, 1);
}

/**
 * Format score from structural health.
 *
 * Empty → 0
 * Truncated without closing punctuation → -25
 * Ends with sentence punctuation → +25
 * Low 4-gram repetition (<15%): +25 | moderate (<30%): +10 | high: -20
 */
export function formatScore(
  completionText: string,
  wasTruncated = false
): number {
  const text = completionText.trim();
  if (!text) return 0;

  let score = 50;

  if (/[.!?…]$/.test(text) || text.endsWith("```")) {
    score += 25;
  } else if (wasTruncated) {
    score -= 25;
  } else {
    score -= 10;
  }

  const rep = repetitionRatio(text);
  if (rep < 0.15) score += 25;
  else if (rep < 0.3) score += 10;
  else score -= 20;

  return clamp(Math.round(score), 0, 100);
}

export function compositeScore(
  latency: number,
  length: number,
  format: number
): number {
  const raw =
    latency * WEIGHTS.latency +
    length * WEIGHTS.length +
    format * WEIGHTS.format;
  return Math.round(raw);
}

export function decisionFromComposite(composite: number): Decision {
  if (composite >= THRESHOLDS.accept) return "accept";
  if (composite >= THRESHOLDS.review) return "review";
  return "reject";
}

export function scoreResponse(input: ScoreInput): ScoreResult {
  const latency = latencyScore(input.ttftMs, input.tokensPerSec);
  const length = lengthScore(input.promptTokens, input.completionTokens);
  const format = formatScore(input.completionText, input.wasTruncated ?? false);
  const composite = compositeScore(latency, length, format);

  return {
    latencyScore: latency,
    lengthScore: length,
    formatScore: format,
    composite,
    decision: decisionFromComposite(composite),
  };
}

export const SCORING_META = {
  weights: WEIGHTS,
  thresholds: THRESHOLDS,
} as const;

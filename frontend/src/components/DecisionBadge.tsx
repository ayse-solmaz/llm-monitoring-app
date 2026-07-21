import type { ScoreResult, Decision } from "@/lib/scoring";

export const decisionStyles: Record<
  Decision,
  { label: string; className: string }
> = {
  accept: {
    label: "Accept",
    className: "bg-green-100 text-green-800",
  },
  review: {
    label: "Review",
    className: "bg-amber-100 text-amber-900",
  },
  reject: {
    label: "Reject",
    className: "bg-red-100 text-red-800",
  },
};

export default function DecisionBadge({
  decision,
  composite,
}: {
  decision: Decision;
  composite?: number;
}) {
  const style = decisionStyles[decision];
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${style.className}`}
    >
      {style.label}
      {composite !== undefined ? ` · ${composite}` : ""}
    </span>
  );
}

export function apiScoreToScoreResult(score: {
  latency_score: number;
  length_score: number;
  format_score: number;
  composite: number;
  decision: Decision;
}): ScoreResult {
  return {
    latencyScore: score.latency_score,
    lengthScore: score.length_score,
    formatScore: score.format_score,
    composite: score.composite,
    decision: score.decision,
  };
}

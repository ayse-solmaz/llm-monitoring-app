import type { ScoreResult, Decision } from "@/lib/scoring";

const decisionStyles: Record<
  Decision,
  { label: string; className: string }
> = {
  accept: {
    label: "Accept",
    className: "bg-green-100 text-green-900 border-green-300",
  },
  review: {
    label: "Review",
    className: "bg-amber-100 text-amber-900 border-amber-300",
  },
  reject: {
    label: "Reject",
    className: "bg-red-100 text-red-900 border-red-300",
  },
};

export default function ScoreCard({ score }: { score: ScoreResult }) {
  const style = decisionStyles[score.decision];

  return (
    <div className="mt-2 rounded border bg-white p-3 text-xs">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="font-medium text-gray-700">Decision score</span>
        <span
          className={`rounded border px-2 py-0.5 font-semibold uppercase ${style.className}`}
        >
          {style.label} · {score.composite}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-gray-600">
        <div>
          <p className="text-[10px] uppercase tracking-wide text-gray-400">
            Latency
          </p>
          <p className="font-mono font-medium">{score.latencyScore}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-gray-400">
            Length
          </p>
          <p className="font-mono font-medium">{score.lengthScore}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide text-gray-400">
            Format
          </p>
          <p className="font-mono font-medium">{score.formatScore}</p>
        </div>
      </div>
      <p className="mt-2 text-[10px] text-gray-400">
        Composite: 0.4×latency + 0.3×length + 0.3×format
      </p>
    </div>
  );
}

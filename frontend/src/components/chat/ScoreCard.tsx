import type { ScoreResult } from "@/lib/scoring";
import DecisionBadge from "@/components/DecisionBadge";

export default function ScoreCard({ score }: { score: ScoreResult }) {
  return (
    <div className="mt-2 rounded-xl bg-white/40 backdrop-blur-sm border border-white/45 p-3 text-[13px] text-ink">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="font-medium text-ink">Decision score</span>
        <DecisionBadge decision={score.decision} composite={score.composite} />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div>
          <p className="text-[11px] font-medium text-ink-muted">Latency</p>
          <p className="font-mono text-[15px] font-semibold text-ink">
            {score.latencyScore}
          </p>
        </div>
        <div>
          <p className="text-[11px] font-medium text-ink-muted">Length</p>
          <p className="font-mono text-[15px] font-semibold text-ink">
            {score.lengthScore}
          </p>
        </div>
        <div>
          <p className="text-[11px] font-medium text-ink-muted">Format</p>
          <p className="font-mono text-[15px] font-semibold text-ink">
            {score.formatScore}
          </p>
        </div>
      </div>
      <p className="mt-2 text-[11px] text-ink-muted">
        Composite: 0.4×latency + 0.3×length + 0.3×format
      </p>
    </div>
  );
}

"use client";

import RichResult from "@/components/chat/RichResult";
import { RICH_CHART_SAMPLE } from "@/lib/rich-chart";

/** Standalone smoke-test page for Rich Result charts (no MLC / auth required). */
export default function RichPreviewPage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="mb-2 text-xl font-semibold text-ink">Rich Result preview</h1>
      <p className="mb-6 text-sm text-ink-muted">
        Sample assistant message with line and bar charts (FINAL BOSS Rich Result).
      </p>
      <div className="bubble-assistant inline-block max-w-full px-4 py-3">
        <RichResult content={RICH_CHART_SAMPLE} />
      </div>
    </main>
  );
}

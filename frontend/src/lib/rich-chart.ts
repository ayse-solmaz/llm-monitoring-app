import { z } from "zod";

/** JSON inside a ```chart fenced block (Rich Result). */
export const chartSpecSchema = z.object({
  type: z.enum(["line", "bar"]),
  title: z.string().optional(),
  xKey: z.string().optional(),
  yKey: z.string().optional(),
  data: z
    .array(z.record(z.string(), z.union([z.string(), z.number()])))
    .min(1),
});

export type ChartSpec = z.infer<typeof chartSpecSchema> & {
  xKey: string;
  yKey: string;
};

export type RichSegment =
  | { type: "markdown"; content: string }
  | { type: "chart"; spec: ChartSpec };

export function parseChartSpec(raw: string): ChartSpec | null {
  try {
    const parsed = chartSpecSchema.safeParse(JSON.parse(raw));
    if (!parsed.success) return null;
    const { xKey, yKey, ...rest } = parsed.data;
    return {
      ...rest,
      xKey: xKey ?? "name",
      yKey: yKey ?? "value",
    };
  } catch {
    return null;
  }
}

/** Split assistant markdown into markdown segments and chart blocks. */
export function parseRichSegments(md: string): RichSegment[] {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const segments: RichSegment[] = [];
  const textBuf: string[] = [];

  const flushText = () => {
    if (textBuf.length === 0) return;
    segments.push({ type: "markdown", content: textBuf.join("\n") });
    textBuf.length = 0;
  };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const fence = /^```(\w*)/.exec(line);
    if (fence) {
      const lang = fence[1];
      i += 1;
      const codeBuf: string[] = [];
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeBuf.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;

      const body = codeBuf.join("\n");
      if (lang === "chart") {
        flushText();
        const spec = parseChartSpec(body);
        if (spec) {
          segments.push({ type: "chart", spec });
        } else {
          textBuf.push(`\`\`\`chart\n${body}\n\`\`\``);
        }
      } else {
        textBuf.push(`\`\`\`${lang}\n${body}\n\`\`\``);
      }
      continue;
    }

    textBuf.push(line);
    i += 1;
  }

  flushText();
  return segments.length > 0 ? segments : [{ type: "markdown", content: md }];
}

/** Sample Rich Result with line + bar charts (smoke test / preview). */
export const RICH_CHART_SAMPLE = `## Decode throughput

Below is a **line chart** of tokens/sec across decode steps:

\`\`\`chart
{
  "type": "line",
  "title": "Tokens/sec by step",
  "xKey": "step",
  "yKey": "tps",
  "data": [
    { "step": "1", "tps": 8.2 },
    { "step": "2", "tps": 11.5 },
    { "step": "3", "tps": 14.1 },
    { "step": "4", "tps": 12.8 }
  ]
}
\`\`\`

Score breakdown (bar chart):

\`\`\`chart
{
  "type": "bar",
  "title": "Decision score components",
  "data": [
    { "name": "Latency", "value": 78 },
    { "name": "Length", "value": 65 },
    { "name": "Format", "value": 92 }
  ]
}
\`\`\`
`;

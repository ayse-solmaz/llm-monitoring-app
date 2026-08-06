"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartSpec } from "@/lib/rich-chart";

const CHART_AXIS = "#001D39";
const CHART_GRID = "rgba(73, 118, 159, 0.35)";
const CHART_LINE = "#0A4174";
const CHART_FILL = "#7BBDE8";

const TOOLTIP_STYLE = {
  backgroundColor: "rgba(255, 255, 255, 0.92)",
  border: "1px solid rgba(255, 255, 255, 0.5)",
  borderRadius: "12px",
  fontSize: "13px",
  color: CHART_AXIS,
};

type Props = {
  spec: ChartSpec;
};

export default function RichResultChart({ spec }: Props) {
  const { type, title, xKey, yKey, data } = spec;

  return (
    <figure className="rich-chart my-3">
      {title ? (
        <figcaption className="rich-chart-title mb-2 text-sm font-medium text-ink">
          {title}
        </figcaption>
      ) : null}
      <div className="rich-chart-body h-[220px] w-full min-w-0 rounded-lg bg-white/40 p-2">
        <ResponsiveContainer width="100%" height="100%">
          {type === "line" ? (
            <LineChart data={data}>
              <CartesianGrid stroke={CHART_GRID} strokeDasharray="3 3" />
              <XAxis
                dataKey={xKey}
                tick={{ fontSize: 11, fill: CHART_AXIS }}
              />
              <YAxis tick={{ fontSize: 11, fill: CHART_AXIS }} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Line
                type="monotone"
                dataKey={yKey}
                stroke={CHART_LINE}
                strokeWidth={2}
                dot={{ r: 3, fill: CHART_LINE }}
              />
            </LineChart>
          ) : (
            <BarChart data={data}>
              <CartesianGrid stroke={CHART_GRID} strokeDasharray="3 3" />
              <XAxis
                dataKey={xKey}
                tick={{ fontSize: 11, fill: CHART_AXIS }}
              />
              <YAxis tick={{ fontSize: 11, fill: CHART_AXIS }} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey={yKey} fill={CHART_FILL} radius={[6, 6, 0, 0]} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

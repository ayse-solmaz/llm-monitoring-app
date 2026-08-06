"use client";

/**
 * Rich Result — lightweight Markdown → HTML for assistant replies (FINAL BOSS).
 * Charts: fenced ```chart blocks with JSON (see lib/rich-chart.ts).
 * No extra markdown library (approved stack).
 */

import { parseRichSegments } from "@/lib/rich-chart";
import RichResultChart from "@/components/chat/RichResultChart";

type Props = {
  content: string;
  className?: string;
};

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inlineFormat(text: string): string {
  let s = escapeHtml(text);
  s = s.replace(/`([^`]+)`/g, "<code class=\"rich-code-inline\">$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  return s;
}

/** Convert a subset of Markdown to safe HTML. */
export function markdownToHtml(md: string): string {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const out: string[] = [];
  let i = 0;
  let inCode = false;
  let codeBuf: string[] = [];
  let inList = false;

  const closeList = () => {
    if (inList) {
      out.push("</ul>");
      inList = false;
    }
  };

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("```")) {
      if (inCode) {
        out.push(
          `<pre class="rich-pre"><code>${escapeHtml(codeBuf.join("\n"))}</code></pre>`
        );
        codeBuf = [];
        inCode = false;
      } else {
        closeList();
        inCode = true;
      }
      i += 1;
      continue;
    }

    if (inCode) {
      codeBuf.push(line);
      i += 1;
      continue;
    }

    // Table row
    if (line.includes("|") && line.trim().startsWith("|")) {
      closeList();
      const rows: string[] = [];
      while (i < lines.length && lines[i].includes("|")) {
        const raw = lines[i].trim();
        if (/^\|[-:\s|]+\|$/.test(raw)) {
          i += 1;
          continue;
        }
        const cells = raw
          .split("|")
          .slice(1, -1)
          .map((c) => `<td class="rich-td">${inlineFormat(c.trim())}</td>`);
        rows.push(`<tr>${cells.join("")}</tr>`);
        i += 1;
      }
      out.push(`<table class="rich-table"><tbody>${rows.join("")}</tbody></table>`);
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      closeList();
      const level = heading[1].length;
      out.push(
        `<h${level} class="rich-h${level}">${inlineFormat(heading[2])}</h${level}>`
      );
      i += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      if (!inList) {
        out.push('<ul class="rich-ul">');
        inList = true;
      }
      out.push(
        `<li>${inlineFormat(line.replace(/^[-*]\s+/, ""))}</li>`
      );
      i += 1;
      continue;
    }

    if (!line.trim()) {
      closeList();
      out.push("<br />");
      i += 1;
      continue;
    }

    closeList();
    out.push(`<p class="rich-p">${inlineFormat(line)}</p>`);
    i += 1;
  }

  if (inCode) {
    out.push(
      `<pre class="rich-pre"><code>${escapeHtml(codeBuf.join("\n"))}</code></pre>`
    );
  }
  closeList();
  return out.join("\n");
}

export default function RichResult({ content, className = "" }: Props) {
  if (!content) {
    return <span className={`animate-pulse ${className}`}>…</span>;
  }

  const segments = parseRichSegments(content);

  return (
    <div className={`rich-result text-left ${className}`}>
      {segments.map((segment, index) =>
        segment.type === "chart" ? (
          <RichResultChart key={`chart-${index}`} spec={segment.spec} />
        ) : (
          <div
            key={`md-${index}`}
            dangerouslySetInnerHTML={{
              __html: markdownToHtml(segment.content),
            }}
          />
        )
      )}
    </div>
  );
}

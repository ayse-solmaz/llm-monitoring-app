/**
 * Frontend WebMCP-style payload builder (FINAL BOSS).
 *
 * Gemma 2B-IT: no reliable `system` role. Keep prompts SHORT on CPU.
 * Adapter ids match peft-adapters/ folders (soft hot-swap via prompt style).
 */

import {
  formatWikiContext,
  searchDeepKwiki,
  type WikiHit,
} from "@/lib/deepkwiki";
import type { ChatMessage } from "@/lib/mlc-server";

export type WebMcpAdminOpts = {
  systemPrompt: string;
  temperature: number;
  topP: number;
  maxTokens: number;
  adapterId: string;
  deepKwikiEnabled: boolean;
};

export type WebMcpBundle = {
  messages: ChatMessage[];
  wikiHits: WikiHit[];
  temperature: number;
  topP: number;
  maxTokens: number;
  adapterId: string;
};

const MAX_HISTORY = 0;

const ADAPTER_STYLE: Record<string, string> = {
  deepkwiki: "Short factual answer about this LLM monitoring stack.",
  "code-assistant": "Short code help only.",
};

/** Build minimal user messages for CPU Gemma (long prompts → nginx 504). */
export function buildWebMcpMessages(
  history: Array<{ role: "user" | "assistant"; content: string }>,
  userText: string,
  opts: WebMcpAdminOpts
): WebMcpBundle {
  const wikiHits = opts.deepKwikiEnabled
    ? searchDeepKwiki(userText, 1)
    : [];
  const wikiBlock = formatWikiContext(wikiHits).slice(0, 280);
  const adapterHint = ADAPTER_STYLE[opts.adapterId] ?? "";

  const recent = history.slice(-MAX_HISTORY).map((m) => ({
    role: m.role as "user" | "assistant",
    content: m.content.slice(0, 200),
  }));

  const parts: string[] = [];
  if (adapterHint) parts.push(adapterHint);
  if (wikiBlock) parts.push(wikiBlock);
  if (!adapterHint && !wikiBlock && opts.systemPrompt.trim()) {
    parts.push(opts.systemPrompt.trim().slice(0, 80));
  }

  const q = userText.slice(0, 200);
  const content =
    parts.length > 0
      ? `${parts.join("\n")}\nQ: ${q}\nA (one short sentence):`
      : q;

  const messages: ChatMessage[] = [
    ...recent,
    { role: "user", content },
  ];

  return {
    messages,
    wikiHits,
    temperature: opts.temperature,
    topP: opts.topP,
    maxTokens: Math.min(opts.maxTokens, 24),
    adapterId: opts.adapterId,
  };
}

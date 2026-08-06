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
  deepkwiki: "Bu LLM izleme yığını hakkında kısa, doğru Türkçe cevap ver.",
  "code-assistant": "Kısa kod yardımı, Türkçe açıkla.",
};

const ENV_MAX = Number(process.env.NEXT_PUBLIC_MAX_TOKENS || "256");
const MAX_TOKENS_CAP = Math.min(Math.max(ENV_MAX, 1), 512);

/** Build user messages for Gemma (no reliable system role — fold into user). */
export function buildWebMcpMessages(
  history: Array<{ role: "user" | "assistant"; content: string }>,
  userText: string,
  opts: WebMcpAdminOpts
): WebMcpBundle {
  const wikiHits = opts.deepKwikiEnabled
    ? searchDeepKwiki(userText, 1)
    : [];
  // Keep facts intact; truncate only oversized multi-hit blocks.
  const wikiBlock = formatWikiContext(wikiHits).slice(0, 360);
  const adapterHint = ADAPTER_STYLE[opts.adapterId] ?? "";

  const recent = history.slice(-MAX_HISTORY).map((m) => ({
    role: m.role as "user" | "assistant",
    content: m.content.slice(0, 400),
  }));

  // Gemma-2B-IT is weak on Turkish factual Qs; keep prompt minimal.
  // Prefer short system bias without a completion-cue suffix that derails decoding.
  const parts: string[] = [];
  if (opts.systemPrompt.trim()) {
    parts.push(opts.systemPrompt.trim().slice(0, 80));
  }
  if (adapterHint) parts.push(adapterHint.slice(0, 80));
  if (wikiBlock) parts.push(wikiBlock);

  const q = userText.slice(0, 400);
  // Gemma-2B-IT often fails pure-Turkish factoids (e.g. capital→Istanbul/Abuja)
  // but answers correctly when an English accuracy cue is present.
  const looksTurkish = /[ğüşıöçĞÜŞİÖÇ]/u.test(q) || /\b(nedir|neresi|kaç|nasıl)\b/i.test(q);
  const accuracyCue = looksTurkish
    ? "Answer with the correct well-known fact. Be brief."
    : "";
  const rules = [...parts, accuracyCue].filter(Boolean);
  const content =
    rules.length > 0 ? `${q}\n\n(${rules.join("; ")})` : q;

  const messages: ChatMessage[] = [
    ...recent,
    { role: "user", content },
  ];

  return {
    messages,
    wikiHits,
    temperature: opts.temperature,
    topP: opts.topP,
    maxTokens: Math.min(opts.maxTokens, MAX_TOKENS_CAP),
    adapterId: opts.adapterId,
  };
}

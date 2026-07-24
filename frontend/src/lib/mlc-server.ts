/**
 * Server-side MLC-LLM client (OpenAI-compatible via nginx :8080).
 * Browser WebLLM remains on /spike only.
 */

export const MLC_BASE_URL =
  process.env.NEXT_PUBLIC_MLC_URL?.replace(/\/$/, "") ||
  "http://localhost:8080";

export const MLC_MODEL_ID = "gemma-2b-it";

export type ChatMessage = {
  role: "system" | "user" | "assistant";
  content: string;
};

export type StreamCompletionResult = {
  content: string;
  promptTokens: number;
  completionTokens: number;
  ttftMs: number;
  totalMs: number;
  tokensPerSec: number;
};

export type StreamHandlers = {
  onToken?: (delta: string, full: string) => void;
  onUsage?: (promptTokens: number, completionTokens: number) => void;
};

/** True if the MLC nginx front door responds (GET /v1/models). */
export async function checkMlcServerHealth(
  timeoutMs = 5000
): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    // Prefer GET /v1/models (MLC native). Also allow OPTIONS for CORS preflight probes.
    const res = await fetch(`${MLC_BASE_URL}/v1/models`, {
      method: "GET",
      signal: controller.signal,
    });
    return res.ok;
  } catch {
    try {
      const opt = await fetch(`${MLC_BASE_URL}/v1/chat/completions`, {
        method: "OPTIONS",
        signal: controller.signal,
      });
      return opt.ok || opt.status === 204;
    } catch {
      return false;
    }
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Streaming chat completion against server MLC.
 * TTFT = time until first content token (or first SSE data byte with content).
 * tokens/sec = completion_tokens / (totalMs/1000) when usage is present;
 * otherwise estimate from elapsed after first token.
 */
export async function fetchCompletion(
  messages: ChatMessage[],
  handlers: StreamHandlers = {},
  maxTokens = 64
): Promise<StreamCompletionResult> {
  const startTime = performance.now();
  let firstTokenTime: number | null = null;
  let full = "";
  let promptTokens = 0;
  let completionTokens = 0;

  const res = await fetch(`${MLC_BASE_URL}/v1/chat/completions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: MLC_MODEL_ID,
      messages,
      stream: true,
      max_tokens: maxTokens,
      stream_options: { include_usage: true },
    }),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(
      `MLC server error ${res.status}: ${text || res.statusText}`
    );
  }

  if (!res.body) {
    throw new Error("MLC response had no body (streaming unsupported)");
  }

  const reader = res.body
    .pipeThrough(new TextDecoderStream())
    .getReader();

  let buffer = "";

  const handleDataLine = (data: string) => {
    if (data === "[DONE]") return;
    let parsed: {
      choices?: Array<{ delta?: { content?: string } }>;
      usage?: { prompt_tokens?: number; completion_tokens?: number };
    };
    try {
      parsed = JSON.parse(data) as typeof parsed;
    } catch {
      return;
    }

    const delta = parsed.choices?.[0]?.delta?.content ?? "";
    if (delta) {
      if (firstTokenTime === null) {
        firstTokenTime = performance.now();
      }
      full += delta;
      handlers.onToken?.(delta, full);
    }

    if (parsed.usage) {
      if (typeof parsed.usage.prompt_tokens === "number") {
        promptTokens = parsed.usage.prompt_tokens;
      }
      if (typeof parsed.usage.completion_tokens === "number") {
        completionTokens = parsed.usage.completion_tokens;
      }
      handlers.onUsage?.(promptTokens, completionTokens);
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += value;

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      handleDataLine(trimmed.slice(5).trim());
    }
  }

  if (buffer.trim().startsWith("data:")) {
    handleDataLine(buffer.trim().slice(5).trim());
  }

  const totalMs = performance.now() - startTime;
  const ttftMs =
    firstTokenTime !== null ? firstTokenTime - startTime : totalMs;

  if (completionTokens <= 0 && full) {
    // Fallback if stream never sent usage
    completionTokens = Math.max(1, Math.ceil(full.split(/\s+/).length * 1.3));
  }

  const decodeMs =
    firstTokenTime !== null
      ? performance.now() - firstTokenTime
      : totalMs;
  const tokensPerSec =
    completionTokens > 0 && decodeMs > 0
      ? completionTokens / (decodeMs / 1000)
      : 0;

  return {
    content: full,
    promptTokens,
    completionTokens,
    ttftMs,
    totalMs,
    tokensPerSec,
  };
}

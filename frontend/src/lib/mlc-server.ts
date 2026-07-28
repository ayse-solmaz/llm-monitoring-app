/**
 * Server-side MLC-LLM client.
 *
 * Browser always calls same-origin `/api/mlc` (Next.js proxy → gateway).
 * That avoids CORS / Cloudflare quick-tunnel blocking from Vercel pages.
 * Proxy upstream: MLC_UPSTREAM or NEXT_PUBLIC_MLC_URL or localhost:8080.
 */

export const MLC_BASE_URL = "/api/mlc";

export const MLC_MODEL_ID =
  process.env.NEXT_PUBLIC_MLC_MODEL_ID?.trim() || "/app/model";

let cachedModelId: string | null = null;

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

export type CompletionOptions = {
  maxTokens?: number;
  temperature?: number;
  topP?: number;
  adapterId?: string;
  modelId?: string;
};

function friendlyFetchError(err: unknown): Error {
  const msg = err instanceof Error ? err.message : String(err);
  if (/failed to fetch|network error|load failed|aborted/i.test(msg)) {
    return new Error(
      "Network error talking to MLC gateway. Is Docker up? Only one Chat request at a time on CPU — wait or: docker compose restart gateway mlc"
    );
  }
  return err instanceof Error ? err : new Error(msg);
}

/** Resolve the model id MLC actually serves (cached). */
export async function resolveMlcModelId(): Promise<string> {
  if (cachedModelId) return cachedModelId;
  try {
    const res = await fetch(`${MLC_BASE_URL}/v1/models`, { method: "GET" });
    if (res.ok) {
      const json = (await res.json()) as { data?: Array<{ id?: string }> };
      const id = json.data?.[0]?.id?.trim();
      if (id) {
        cachedModelId = id;
        return id;
      }
    }
  } catch {
    // fall through
  }
  cachedModelId = MLC_MODEL_ID;
  return MLC_MODEL_ID;
}

/** True if the MLC front door responds (GET /v1/models). Retries briefly. */
export async function checkMlcServerHealth(
  timeoutMs = 12000
): Promise<boolean> {
  const attempts = 3;
  for (let i = 0; i < attempts; i++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(`${MLC_BASE_URL}/v1/models`, {
        method: "GET",
        signal: controller.signal,
        mode: "cors",
        cache: "no-store",
      });
      if (res.ok) {
        try {
          const json = (await res.json()) as { data?: Array<{ id?: string }> };
          const id = json.data?.[0]?.id?.trim();
          if (id) cachedModelId = id;
        } catch {
          // ignore
        }
        return true;
      }
    } catch {
      // retry
    } finally {
      clearTimeout(timer);
    }
    await new Promise((r) => setTimeout(r, 800 * (i + 1)));
  }
  return false;
}

type ParseState = {
  firstTokenTime: number | null;
  startTime: number;
  full: string;
  promptTokens: number;
  completionTokens: number;
  upstreamError: string | null;
};

function parseSsePayload(
  data: string,
  state: ParseState,
  handlers: StreamHandlers
): void {
  if (data === "[DONE]") return;
  let parsed: {
    error?: { message?: string };
    choices?: Array<{
      delta?: { content?: string | null };
      message?: { content?: string | null };
      text?: string;
    }>;
    usage?: { prompt_tokens?: number; completion_tokens?: number };
  };
  try {
    parsed = JSON.parse(data) as typeof parsed;
  } catch {
    return;
  }

  if (parsed.error?.message) {
    state.upstreamError = parsed.error.message;
    return;
  }

  const choice = parsed.choices?.[0];
  const delta =
    choice?.delta?.content ??
    choice?.message?.content ??
    choice?.text ??
    "";

  if (delta) {
    if (state.firstTokenTime === null) {
      state.firstTokenTime = performance.now();
    }
    state.full += delta;
    handlers.onToken?.(delta, state.full);
  }

  if (parsed.usage) {
    if (typeof parsed.usage.prompt_tokens === "number") {
      state.promptTokens = parsed.usage.prompt_tokens;
    }
    if (typeof parsed.usage.completion_tokens === "number") {
      state.completionTokens = parsed.usage.completion_tokens;
    }
    handlers.onUsage?.(state.promptTokens, state.completionTokens);
  }
}

async function safeReadJson(res: Response): Promise<unknown> {
  const text = await res.text();
  const trimmed = text.trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("<")) {
    throw new Error(
      `MLC/gateway returned HTML instead of JSON (HTTP ${res.status}). MLC is likely busy or timed out — wait for the previous request, then: docker compose restart mlc gateway`
    );
  }
  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    throw new Error(
      `MLC returned non-JSON body (HTTP ${res.status}): ${trimmed.slice(0, 160)}`
    );
  }
}

/**
 * Streaming chat completion. Falls back to non-stream once if stream is empty.
 */
export async function fetchCompletion(
  messages: ChatMessage[],
  handlers: StreamHandlers = {},
  options: number | CompletionOptions = 64
): Promise<StreamCompletionResult> {
  const opts: CompletionOptions =
    typeof options === "number" ? { maxTokens: options } : options;
  const maxTokens = Math.min(opts.maxTokens ?? 16, 24);

  const temperature = opts.temperature ?? 0.35;
  const topP = opts.topP ?? 0.9;
  const model = opts.modelId || (await resolveMlcModelId());

  const startTime = performance.now();
  const state: ParseState = {
    firstTokenTime: null,
    startTime,
    full: "",
    promptTokens: 0,
    completionTokens: 0,
    upstreamError: null,
  };

  let res: Response;
  try {
    res = await fetch(`${MLC_BASE_URL}/v1/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({
        model,
        messages,
        stream: true,
        max_tokens: maxTokens,
        temperature,
        top_p: topP,
      }),
      cache: "no-store",
    });
  } catch (err) {
    throw friendlyFetchError(err);
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    if (text.trim().startsWith("<")) {
      throw new Error(
        `MLC HTTP ${res.status} (HTML). Model busy/timeout — one request at a time; docker compose restart mlc gateway`
      );
    }
    throw new Error(
      `MLC server error ${res.status}: ${text.slice(0, 240) || res.statusText} (model=${model})`
    );
  }

  if (!res.body) {
    throw new Error("MLC response had no body (streaming unsupported)");
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += value;

      // Detect HTML error pages stuffed into the stream
      if (!state.full && buffer.trimStart().startsWith("<")) {
        throw new Error(
          "MLC/gateway streamed an HTML error page (timeout/busy). Restart: docker compose restart mlc gateway"
        );
      }

      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;
        parseSsePayload(trimmed.slice(5).trim(), state, handlers);
      }
    }
  } catch (err) {
    throw friendlyFetchError(err);
  }

  if (buffer.trim().startsWith("data:")) {
    parseSsePayload(buffer.trim().slice(5).trim(), state, handlers);
  }

  if (state.upstreamError) {
    throw new Error(state.upstreamError);
  }

  if (!state.full.trim()) {
    try {
      const fallback = await fetchCompletionNonStream(messages, {
        ...opts,
        modelId: model,
        maxTokens,
        temperature,
        topP,
      });
      if (fallback.content.trim()) {
        handlers.onToken?.(fallback.content, fallback.content);
        handlers.onUsage?.(fallback.promptTokens, fallback.completionTokens);
        return fallback;
      }
    } catch (err) {
      throw friendlyFetchError(err);
    }
    throw new Error(
      `MLC returned empty text (model=${model}). Wait — CPU is slow; only one message at a time. Or: docker compose restart mlc gateway && docker compose up -d --scale mlc=1`
    );
  }

  const totalMs = performance.now() - startTime;
  const ttftMs =
    state.firstTokenTime !== null
      ? state.firstTokenTime - startTime
      : totalMs;

  let { completionTokens } = state;
  const promptTokens = state.promptTokens;
  if (completionTokens <= 0 && state.full) {
    completionTokens = Math.max(1, Math.ceil(state.full.split(/\s+/).length * 1.3));
  }

  const decodeMs =
    state.firstTokenTime !== null
      ? performance.now() - state.firstTokenTime
      : totalMs;
  const tokensPerSec =
    completionTokens > 0 && decodeMs > 0
      ? completionTokens / (decodeMs / 1000)
      : 0;

  return {
    content: state.full,
    promptTokens,
    completionTokens,
    ttftMs,
    totalMs,
    tokensPerSec,
  };
}

async function fetchCompletionNonStream(
  messages: ChatMessage[],
  opts: CompletionOptions
): Promise<StreamCompletionResult> {
  const startTime = performance.now();
  const model = opts.modelId || (await resolveMlcModelId());
  const maxTokens = Math.min(opts.maxTokens ?? 16, 24);


  let res: Response;
  try {
    res = await fetch(`${MLC_BASE_URL}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model,
        messages,
        stream: false,
        max_tokens: maxTokens,
        temperature: opts.temperature ?? 0.35,
        top_p: opts.topP ?? 0.9,
      }),
    });
  } catch (err) {
    throw friendlyFetchError(err);
  }

  const json = (await safeReadJson(res)) as {
    error?: { message?: string };
    choices?: Array<{ message?: { content?: string }; text?: string }>;
    usage?: { prompt_tokens?: number; completion_tokens?: number };
  } | null;

  if (!res.ok) {
    throw new Error(
      json?.error?.message ||
        `MLC non-stream error ${res.status}`
    );
  }

  if (json?.error?.message) {
    throw new Error(json.error.message);
  }

  const content =
    json?.choices?.[0]?.message?.content ?? json?.choices?.[0]?.text ?? "";
  const totalMs = performance.now() - startTime;
  const promptTokens = json?.usage?.prompt_tokens ?? 0;
  const completionTokens =
    json?.usage?.completion_tokens ??
    (content
      ? Math.max(1, Math.ceil(content.split(/\s+/).length * 1.3))
      : 0);

  return {
    content,
    promptTokens,
    completionTokens,
    ttftMs: totalMs,
    totalMs,
    tokensPerSec:
      completionTokens > 0 && totalMs > 0
        ? completionTokens / (totalMs / 1000)
        : 0,
  };
}

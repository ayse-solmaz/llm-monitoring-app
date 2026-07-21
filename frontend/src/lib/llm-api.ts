import { apiFetch } from "@/lib/api";
import type { ScoreResult } from "@/lib/scoring";
import type {
  ApiMessage,
  ApiScore,
  ApiSession,
  ApiSessionDetail,
  MetricsSummary,
  ScoresSummary,
  SessionsListData,
} from "@/lib/types";
import { showErrorToast } from "@/store/toastStore";

export function getDeviceInfo(): string {
  if (typeof navigator === "undefined") return "unknown";
  return navigator.userAgent;
}

export function persistSession(
  modelId: string,
  modelLoadMs: number,
  onCreated: (sessionId: string) => void
): void {
  void apiFetch<ApiSession>("/llm/sessions", {
    method: "POST",
    body: JSON.stringify({
      model_id: modelId,
      device_info: getDeviceInfo(),
      model_load_ms: Math.round(modelLoadMs),
    }),
  })
    .then((session) => onCreated(session.id))
    .catch((err) => showErrorToast("Session save", err));
}

export function persistUserMessage(sessionId: string, content: string): void {
  void apiFetch<ApiMessage>(`/llm/sessions/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({
      role: "user",
      content,
      ttft_ms: 0,
      tokens_prompt: 0,
      tokens_completion: 0,
      tokens_per_sec: 0,
      total_ms: 0,
    }),
  }).catch((err) => showErrorToast("Message save", err));
}

export function persistAssistantResult(
  sessionId: string,
  content: string,
  metrics: {
    ttftMs: number;
    tokensPerSec: number;
    promptTokens: number;
    completionTokens: number;
    totalMs: number;
  },
  score: ScoreResult
): void {
  void (async () => {
    try {
      const message = await apiFetch<ApiMessage>(
        `/llm/sessions/${sessionId}/messages`,
        {
          method: "POST",
          body: JSON.stringify({
            role: "assistant",
            content,
            ttft_ms: Math.round(metrics.ttftMs),
            tokens_prompt: metrics.promptTokens,
            tokens_completion: metrics.completionTokens,
            tokens_per_sec: metrics.tokensPerSec,
            total_ms: Math.round(metrics.totalMs),
          }),
        }
      );

      await apiFetch<ApiScore>(`/llm/sessions/${sessionId}/scores`, {
        method: "POST",
        body: JSON.stringify({
          message_id: message.id,
          latency_score: score.latencyScore,
          length_score: score.lengthScore,
          format_score: score.formatScore,
          composite: score.composite,
          decision: score.decision,
        }),
      });
    } catch (err) {
      showErrorToast("Save metrics", err);
    }
  })();
}

export function fetchSessions(page: number, limit: number) {
  return apiFetch<SessionsListData>(
    `/llm/sessions?page=${page}&limit=${limit}`
  );
}

export function fetchSessionDetail(sessionId: string) {
  return apiFetch<ApiSessionDetail>(`/llm/sessions/${sessionId}`);
}

export function fetchMetricsSummary() {
  return apiFetch<MetricsSummary>("/llm/metrics/summary");
}

export function fetchScoresSummary() {
  return apiFetch<ScoresSummary>("/llm/scores/summary");
}

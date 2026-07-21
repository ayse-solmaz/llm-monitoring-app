import type { ScoreResult } from "@/lib/scoring";

export type ApiError = {
  code: string;
  message: string;
};

export type ApiEnvelope<T> = {
  data: T | null;
  error: ApiError | null;
};

export type TokenData = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};

export type RefreshData = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};

export type UserData = {
  id: string;
  email: string;
  name: string;
  created_at: string;
};

export type ModelInfo = {
  id: string;
  size: string;
  recommended_device: string;
};

export type ModelsData = {
  models: ModelInfo[];
};

export type MessageMetrics = {
  ttftMs: number;
  tokensPerSec: number;
  promptTokens: number;
  completionTokens: number;
  totalMs: number;
  modelLoadMs: number | null;
  runtimeStatsText: string | null;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  metrics?: MessageMetrics;
  score?: ScoreResult;
};

export type LiveMetrics = {
  ttftMs: number | null;
  tokensPerSec: number | null;
  promptTokens: number | null;
  completionTokens: number | null;
  elapsedMs: number;
  modelLoadMs: number | null;
  runtimeStatsText: string | null;
  isStreaming: boolean;
};

export type ApiSession = {
  id: string;
  user_id: string;
  model_id: string;
  device_info: string;
  model_load_ms: number | null;
  created_at: string;
};

export type ApiMessage = {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  ttft_ms: number;
  tokens_prompt: number;
  tokens_completion: number;
  tokens_per_sec: number;
  total_ms: number;
  created_at: string;
  score?: ApiScore;
};

export type ApiScore = {
  id: string;
  message_id: string;
  latency_score: number;
  length_score: number;
  format_score: number;
  composite: number;
  decision: ScoreResult["decision"];
  created_at: string;
};

export type ApiSessionDetail = ApiSession & {
  messages: ApiMessage[];
};

export type SessionsListData = {
  sessions: ApiSession[];
  page: number;
  limit: number;
  total: number;
};

export type MetricsSummary = {
  avg_ttft_ms: number | null;
  avg_tokens_per_sec: number | null;
  total_tokens: number;
  session_count: number;
};

export type ScoresSummary = {
  avg_composite: number | null;
  by_decision: Record<ScoreResult["decision"], number>;
};

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

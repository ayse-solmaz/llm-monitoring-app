import { apiFetch } from "@/lib/api";

/** Server-persisted FINAL BOSS admin LLM settings (GET/PUT /admin/llm-settings). */
export type LlmAdminSettings = {
  system_prompt: string;
  temperature: number;
  top_p: number;
  max_tokens: number;
  adapter_id: string;
  deep_kwiki_enabled: boolean;
  updated_at?: string;
};

export async function fetchLlmAdminSettings(): Promise<LlmAdminSettings> {
  return apiFetch<LlmAdminSettings>("/admin/llm-settings");
}

export async function saveLlmAdminSettings(
  settings: Omit<LlmAdminSettings, "updated_at">
): Promise<LlmAdminSettings> {
  return apiFetch<LlmAdminSettings>("/admin/llm-settings", {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}

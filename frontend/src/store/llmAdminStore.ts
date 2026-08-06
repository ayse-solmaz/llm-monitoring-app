/**
 * FINAL BOSS — Admin LLM controls.
 * Persists to backend (/admin/llm-settings) with localStorage cache for offline fallback.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  fetchLlmAdminSettings,
  saveLlmAdminSettings,
  type LlmAdminSettings,
} from "@/lib/llm-admin-api";

export type LlmAdminState = {
  systemPrompt: string;
  temperature: number;
  topP: number;
  maxTokens: number;
  /** Label of PEFT adapter under peft-adapters/ (empty = base model). */
  adapterId: string;
  deepKwikiEnabled: boolean;
  hydrated: boolean;
  saving: boolean;
  dirty: boolean;
  lastSavedAt: string | null;
  syncError: string | null;
  setSystemPrompt: (v: string) => void;
  setTemperature: (v: number) => void;
  setTopP: (v: number) => void;
  setMaxTokens: (v: number) => void;
  setAdapterId: (v: string) => void;
  setDeepKwikiEnabled: (v: boolean) => void;
  applyRemote: (remote: LlmAdminSettings) => void;
  hydrateFromApi: () => Promise<void>;
  saveToApi: () => Promise<void>;
  resetDefaults: () => void;
};

const DEFAULTS = {
  systemPrompt:
    "Answer briefly and accurately. Prefer Turkish when the user writes Turkish.",
  temperature: 0.0,
  topP: 0.9,
  maxTokens: 48,
  adapterId: "",
  deepKwikiEnabled: true,
};

/**
 * Bump when DEFAULTS change so old localStorage values reset.
 * v10: backend sync via /admin/llm-settings.
 */
const ADMIN_STORE_VERSION = 10;

function remoteToLocal(remote: LlmAdminSettings) {
  return {
    systemPrompt: remote.system_prompt,
    temperature: remote.temperature,
    topP: remote.top_p,
    maxTokens: remote.max_tokens,
    adapterId: remote.adapter_id,
    deepKwikiEnabled: remote.deep_kwiki_enabled,
    lastSavedAt: remote.updated_at ?? null,
  };
}

function localToRemote(state: LlmAdminState): Omit<LlmAdminSettings, "updated_at"> {
  return {
    system_prompt: state.systemPrompt,
    temperature: state.temperature,
    top_p: state.topP,
    max_tokens: state.maxTokens,
    adapter_id: state.adapterId,
    deep_kwiki_enabled: state.deepKwikiEnabled,
  };
}

function markDirty<T extends LlmAdminState>(
  set: (partial: Partial<LlmAdminState>) => void,
  patch: Partial<LlmAdminState>
) {
  set({ ...patch, dirty: true, syncError: null });
}

export const useLlmAdminStore = create<LlmAdminState>()(
  persist(
    (set, get) => ({
      ...DEFAULTS,
      hydrated: false,
      saving: false,
      dirty: false,
      lastSavedAt: null,
      syncError: null,
      setSystemPrompt: (systemPrompt) => markDirty(set, { systemPrompt }),
      setTemperature: (temperature) => markDirty(set, { temperature }),
      setTopP: (topP) => markDirty(set, { topP }),
      setMaxTokens: (maxTokens) => markDirty(set, { maxTokens }),
      setAdapterId: (adapterId) => markDirty(set, { adapterId }),
      setDeepKwikiEnabled: (deepKwikiEnabled) => markDirty(set, { deepKwikiEnabled }),
      applyRemote: (remote) =>
        set({
          ...remoteToLocal(remote),
          hydrated: true,
          dirty: false,
          syncError: null,
        }),
      hydrateFromApi: async () => {
        try {
          const remote = await fetchLlmAdminSettings();
          get().applyRemote(remote);
        } catch (err) {
          const message =
            err instanceof Error ? err.message : "Failed to load admin settings";
          set({ hydrated: true, syncError: message });
        }
      },
      saveToApi: async () => {
        set({ saving: true, syncError: null });
        try {
          const remote = await saveLlmAdminSettings(localToRemote(get()));
          get().applyRemote(remote);
        } catch (err) {
          const message =
            err instanceof Error ? err.message : "Failed to save admin settings";
          set({ saving: false, syncError: message });
          throw err;
        } finally {
          set({ saving: false });
        }
      },
      resetDefaults: () =>
        set({ ...DEFAULTS, dirty: true, syncError: null, lastSavedAt: null }),
    }),
    {
      name: "final-boss-llm-admin",
      version: ADMIN_STORE_VERSION,
      migrate: () => ({ ...DEFAULTS }),
      partialize: (state) => ({
        systemPrompt: state.systemPrompt,
        temperature: state.temperature,
        topP: state.topP,
        maxTokens: state.maxTokens,
        adapterId: state.adapterId,
        deepKwikiEnabled: state.deepKwikiEnabled,
        lastSavedAt: state.lastSavedAt,
      }),
    }
  )
);

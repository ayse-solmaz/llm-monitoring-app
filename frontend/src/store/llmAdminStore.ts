/**
 * FINAL BOSS — Admin LLM controls (local, no new backend endpoints).
 * Persists in localStorage so Docker MLC chat can apply hot settings without rebuild.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type LlmAdminState = {
  systemPrompt: string;
  temperature: number;
  topP: number;
  maxTokens: number;
  /** Label of PEFT adapter under peft-adapters/ (empty = base model). */
  adapterId: string;
  deepKwikiEnabled: boolean;
  setSystemPrompt: (v: string) => void;
  setTemperature: (v: number) => void;
  setTopP: (v: number) => void;
  setMaxTokens: (v: number) => void;
  setAdapterId: (v: string) => void;
  setDeepKwikiEnabled: (v: boolean) => void;
  resetDefaults: () => void;
};

const DEFAULTS = {
  systemPrompt: "Answer in one short sentence.",
  temperature: 0.3,
  topP: 0.9,
  maxTokens: 16,
  adapterId: "",
  deepKwikiEnabled: false,
};

/**
 * Bump when DEFAULTS change so old localStorage values reset.
 * v4: shorter defaults to avoid nginx 504 (CPU TTFT > 300s).
 */
const ADMIN_STORE_VERSION = 4;

export const useLlmAdminStore = create<LlmAdminState>()(
  persist(
    (set) => ({
      ...DEFAULTS,
      setSystemPrompt: (systemPrompt) => set({ systemPrompt }),
      setTemperature: (temperature) => set({ temperature }),
      setTopP: (topP) => set({ topP }),
      setMaxTokens: (maxTokens) => set({ maxTokens }),
      setAdapterId: (adapterId) => set({ adapterId }),
      setDeepKwikiEnabled: (deepKwikiEnabled) => set({ deepKwikiEnabled }),
      resetDefaults: () => set({ ...DEFAULTS }),
    }),
    {
      name: "final-boss-llm-admin",
      version: ADMIN_STORE_VERSION,
      migrate: () => ({ ...DEFAULTS }),
    }
  )
);

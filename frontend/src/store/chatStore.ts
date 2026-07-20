import { create } from "zustand";
import type { InitProgressReport } from "@mlc-ai/web-llm";
import type { ChatMessage, LiveMetrics } from "@/lib/types";

const emptyLiveMetrics = (): LiveMetrics => ({
  ttftMs: null,
  tokensPerSec: null,
  promptTokens: null,
  completionTokens: null,
  elapsedMs: 0,
  modelLoadMs: null,
  runtimeStatsText: null,
  isStreaming: false,
});

type ChatState = {
  selectedModelId: string | null;
  modelLoadMs: number | null;
  isModelLoading: boolean;
  isModelReady: boolean;
  loadProgress: InitProgressReport | null;
  loadError: string | null;
  messages: ChatMessage[];
  liveMetrics: LiveMetrics;
  setSelectedModelId: (id: string) => void;
  setModelLoading: (loading: boolean) => void;
  setModelReady: (ready: boolean) => void;
  setLoadProgress: (progress: InitProgressReport | null) => void;
  setLoadError: (error: string | null) => void;
  setModelLoadMs: (ms: number | null) => void;
  addMessage: (message: ChatMessage) => void;
  updateMessage: (id: string, patch: Partial<ChatMessage>) => void;
  setLiveMetrics: (metrics: Partial<LiveMetrics>) => void;
  resetLiveMetrics: () => void;
  clearChat: () => void;
};

export const useChatStore = create<ChatState>((set) => ({
  selectedModelId: null,
  modelLoadMs: null,
  isModelLoading: false,
  isModelReady: false,
  loadProgress: null,
  loadError: null,
  messages: [],
  liveMetrics: emptyLiveMetrics(),

  setSelectedModelId: (id) => set({ selectedModelId: id }),
  setModelLoading: (loading) => set({ isModelLoading: loading }),
  setModelReady: (ready) => set({ isModelReady: ready }),
  setLoadProgress: (progress) => set({ loadProgress: progress }),
  setLoadError: (error) => set({ loadError: error }),
  setModelLoadMs: (ms) => set({ modelLoadMs: ms }),

  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),

  updateMessage: (id, patch) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, ...patch } : m
      ),
    })),

  setLiveMetrics: (metrics) =>
    set((state) => ({
      liveMetrics: { ...state.liveMetrics, ...metrics },
    })),

  resetLiveMetrics: () => set({ liveMetrics: emptyLiveMetrics() }),

  clearChat: () => set({ messages: [], liveMetrics: emptyLiveMetrics() }),
}));

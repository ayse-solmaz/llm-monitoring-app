import { create } from "zustand";

type ToastState = {
  message: string | null;
  showToast: (message: string) => void;
  clearToast: () => void;
};

export const useToastStore = create<ToastState>((set) => ({
  message: null,
  showToast: (message) => set({ message }),
  clearToast: () => set({ message: null }),
}));

export function showErrorToast(label: string, err: unknown) {
  const detail = err instanceof Error ? err.message : "Request failed";
  useToastStore.getState().showToast(`${label}: ${detail}`);
}

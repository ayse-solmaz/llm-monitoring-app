import { create } from "zustand";
import type { UserData } from "@/lib/types";

type AuthState = {
  accessToken: string | null;
  refreshToken: string | null;
  user: UserData | null;
  setSession: (
    accessToken: string,
    refreshToken: string,
    user?: UserData | null
  ) => void;
  setTokens: (accessToken: string, refreshToken: string) => void;
  setAccessToken: (accessToken: string) => void;
  setUser: (user: UserData | null) => void;
  clearSession: () => void;
  isAuthenticated: () => boolean;
};

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken: null,
  refreshToken: null,
  user: null,
  setSession: (accessToken, refreshToken, user = null) =>
    set({ accessToken, refreshToken, user }),
  setTokens: (accessToken, refreshToken) => set({ accessToken, refreshToken }),
  setAccessToken: (accessToken) => set({ accessToken }),
  setUser: (user) => set({ user }),
  clearSession: () => set({ accessToken: null, refreshToken: null, user: null }),
  isAuthenticated: () => Boolean(get().accessToken),
}));

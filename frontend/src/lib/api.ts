import { useAuthStore } from "@/store/authStore";
import type { ApiEnvelope, RefreshData } from "@/lib/types";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080/api/v1";

let refreshInFlight: Promise<boolean> | null = null;

async function parseEnvelope<T>(res: Response): Promise<T> {
  const json = (await res.json()) as ApiEnvelope<T>;
  if (json.error) {
    throw new Error(json.error.message);
  }
  if (json.data === null) {
    throw new Error("Empty response from API");
  }
  return json.data;
}

async function refreshAccessToken(): Promise<boolean> {
  const { refreshToken, setAccessToken, clearSession } = useAuthStore.getState();
  if (!refreshToken) {
    return false;
  }

  try {
    const res = await fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    const data = await parseEnvelope<RefreshData>(res);
    setAccessToken(data.access_token);
    return true;
  } catch {
    clearSession();
    return false;
  }
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  retryOnUnauthorized = true
): Promise<T> {
  const headers = new Headers(options.headers);
  const { accessToken } = useAuthStore.getState();

  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (res.status === 401 && retryOnUnauthorized && accessToken) {
    if (!refreshInFlight) {
      refreshInFlight = refreshAccessToken().finally(() => {
        refreshInFlight = null;
      });
    }
    const refreshed = await refreshInFlight;
    if (refreshed) {
      const newToken = useAuthStore.getState().accessToken;
      if (newToken) {
        headers.set("Authorization", `Bearer ${newToken}`);
      }
      res = await fetch(`${API_URL}${path}`, { ...options, headers });
    }
  }

  const json = (await res.json()) as ApiEnvelope<T>;

  if (json.error) {
    if (res.status === 401 && accessToken) {
      useAuthStore.getState().clearSession();
    }
    throw new Error(json.error.message);
  }

  if (json.data === null) {
    throw new Error("Empty response from API");
  }

  return json.data;
}

export function getApiUrl(): string {
  return API_URL;
}

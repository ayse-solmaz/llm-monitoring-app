"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import type { TokenData, UserData } from "@/lib/types";

type Mode = "login" | "register";

export default function AuthPage() {
  const router = useRouter();
  const accessToken = useAuthStore((s) => s.accessToken);
  const setSession = useAuthStore((s) => s.setSession);
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (accessToken) {
      router.replace("/chat");
    }
  }, [accessToken, router]);

  if (accessToken) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-gray-500">
        Redirecting…
      </div>
    );
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (mode === "register") {
        await apiFetch<UserData>(
          "/auth/register",
          {
            method: "POST",
            body: JSON.stringify({ email, password, name }),
          },
          false
        );
      }

      const tokens = await apiFetch<TokenData>(
        "/auth/login",
        {
          method: "POST",
          body: JSON.stringify({ email, password }),
        },
        false
      );

      setSession(tokens.access_token, tokens.refresh_token);
      router.replace("/chat");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md border rounded-lg p-6 flex flex-col gap-4">
        <h1 className="text-xl font-semibold">LLM Monitoring App</h1>

        <div className="flex gap-2 text-sm">
          <button
            type="button"
            className={`px-3 py-1 rounded border ${mode === "login" ? "bg-gray-100" : ""}`}
            onClick={() => setMode("login")}
          >
            Login
          </button>
          <button
            type="button"
            className={`px-3 py-1 rounded border ${mode === "register" ? "bg-gray-100" : ""}`}
            onClick={() => setMode("register")}
          >
            Register
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          {mode === "register" && (
            <input
              className="border rounded px-3 py-2 text-sm"
              placeholder="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          )}
          <input
            className="border rounded px-3 py-2 text-sm"
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <input
            className="border rounded px-3 py-2 text-sm"
            type="password"
            placeholder="Password (min 8 characters)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="border rounded px-3 py-2 text-sm disabled:opacity-50"
          >
            {loading
              ? "Please wait…"
              : mode === "login"
                ? "Login"
                : "Register & Login"}
          </button>
        </form>
      </div>
    </div>
  );
}

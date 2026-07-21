"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import type { TokenData, UserData } from "@/lib/types";

type Mode = "login" | "register";

type AuthFormProps = {
  title?: string;
  onSuccess?: () => void;
};

export default function AuthForm({
  title = "Sign in",
  onSuccess,
}: AuthFormProps) {
  const router = useRouter();
  const setSession = useAuthStore((s) => s.setSession);
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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
      if (onSuccess) {
        onSuccess();
      } else {
        router.replace("/chat");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="glass-auth-card flex flex-col gap-6">
      <h2 className="text-[32px] font-semibold tracking-tight text-ink">{title}</h2>

      <div className="glass-segmented" role="tablist" aria-label="Authentication mode">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "login"}
          className={`glass-segment ${mode === "login" ? "glass-segment-active" : ""}`}
          onClick={() => setMode("login")}
        >
          Login
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "register"}
          className={`glass-segment ${mode === "register" ? "glass-segment-active" : ""}`}
          onClick={() => setMode("register")}
        >
          Register
        </button>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {mode === "register" && (
          <input
            className="glass-input"
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        )}
        <input
          id="auth-email"
          className="glass-input"
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <input
          className="glass-input"
          type="password"
          placeholder="Password (min 8 characters)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          minLength={8}
          required
        />
        {error && <p className="text-[15px] font-medium text-red-700">{error}</p>}
        <button type="submit" disabled={loading} className="btn-primary w-full py-3">
          {loading ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
      </form>
    </div>
  );
}

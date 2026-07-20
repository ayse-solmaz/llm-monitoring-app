"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import type { UserData } from "@/lib/types";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { accessToken, setUser, clearSession } = useAuthStore();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function verify() {
      if (!accessToken) {
        router.replace("/auth");
        return;
      }

      try {
        const me = await apiFetch<UserData>("/auth/me");
        if (!cancelled) {
          setUser(me);
          setReady(true);
        }
      } catch {
        if (!cancelled) {
          clearSession();
          router.replace("/auth");
        }
      }
    }

    verify();

    return () => {
      cancelled = true;
    };
  }, [accessToken, router, setUser, clearSession]);

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-gray-500">
        Checking session…
      </div>
    );
  }

  return <>{children}</>;
}

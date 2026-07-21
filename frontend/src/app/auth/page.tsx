"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import AuthForm from "@/components/auth/AuthForm";
import AmbientBackground from "@/components/ui/AmbientBackground";
import GlowShell from "@/components/ui/GlowShell";
import { useAuthStore } from "@/store/authStore";

export default function AuthPage() {
  const router = useRouter();
  const accessToken = useAuthStore((s) => s.accessToken);

  useEffect(() => {
    if (accessToken) {
      router.replace("/chat");
    }
  }, [accessToken, router]);

  if (accessToken) {
    return (
      <div className="sky-calm flex min-h-screen items-center justify-center font-system text-[15px] text-ink-muted">
        <AmbientBackground />
        <span className="relative-z">Redirecting…</span>
      </div>
    );
  }

  return (
    <div className="sky-calm min-h-screen font-system relative">
      <AmbientBackground />
      <header className="glass-header relative-z">
        <div className="glass-header-inner">
          <Link href="/" className="text-[17px] font-semibold text-ink">
            LLM Monitoring
          </Link>
          <Link href="/" className="nav-link">
            Back to home
          </Link>
        </div>
      </header>
      <div className="relative-z flex min-h-[calc(100vh-3.5rem)] items-center justify-center px-6 py-16">
        <GlowShell variant="auth" className="w-full max-w-[420px]">
          <AuthForm />
        </GlowShell>
      </div>
    </div>
  );
}

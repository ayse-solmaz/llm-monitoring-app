"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import LandingPage from "@/components/landing/LandingPage";
import { useAuthStore } from "@/store/authStore";

export default function HomePage() {
  const router = useRouter();
  const accessToken = useAuthStore((s) => s.accessToken);

  useEffect(() => {
    if (accessToken) {
      router.replace("/chat");
    }
  }, [accessToken, router]);

  if (accessToken) {
    return (
      <div className="min-h-screen flex items-center justify-center sky-calm text-[15px] text-ink-muted font-system">
        Redirecting…
      </div>
    );
  }

  return <LandingPage />;
}

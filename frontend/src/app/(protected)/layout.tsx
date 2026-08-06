"use client";

import AuthGuard from "@/components/AuthGuard";
import AppShell from "@/components/AppShell";
import LlmAdminHydrator from "@/components/admin/LlmAdminHydrator";
import Toast from "@/components/Toast";

export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <LlmAdminHydrator />
      <AppShell>{children}</AppShell>
      <Toast />
    </AuthGuard>
  );
}

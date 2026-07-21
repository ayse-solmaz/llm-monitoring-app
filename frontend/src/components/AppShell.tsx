"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import AmbientBackground from "@/components/ui/AmbientBackground";

const links = [
  { href: "/chat", label: "Chat" },
  { href: "/dashboard", label: "Dashboard" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { refreshToken, clearSession } = useAuthStore();

  async function handleLogout() {
    if (refreshToken) {
      try {
        await apiFetch("/auth/logout", {
          method: "POST",
          body: JSON.stringify({ refresh_token: refreshToken }),
        }, false);
      } catch {
        // Ignore logout errors; clear local session anyway.
      }
    }
    clearSession();
    router.replace("/");
  }

  return (
    <div className="app-shell sky-calm font-system">
      <AmbientBackground />
      <header className="glass-header relative-z">
        <div className="glass-header-inner">
          <div className="flex items-center gap-8">
            <Link href="/" className="text-[17px] font-semibold text-ink">
              LLM Monitoring
            </Link>
            <nav className="flex gap-6">
              {links.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className={
                    pathname === link.href ? "nav-link-active" : "nav-link"
                  }
                >
                  {link.label}
                </Link>
              ))}
            </nav>
          </div>
          <button type="button" onClick={handleLogout} className="btn-secondary text-[14px]">
            Logout
          </button>
        </div>
      </header>
      <main className="app-main">{children}</main>
    </div>
  );
}

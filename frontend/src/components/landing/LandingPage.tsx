"use client";

import Link from "next/link";
import AuthForm from "@/components/auth/AuthForm";
import FeatureCard from "@/components/landing/FeatureCard";
import AmbientBackground from "@/components/ui/AmbientBackground";
import GlowShell from "@/components/ui/GlowShell";
import ScrollReveal from "@/components/ui/ScrollReveal";

const features = [
  {
    title: "WebGPU inference",
    description:
      "Run Gemma 2B entirely in your browser via WebLLM. No server-side model hosting — your GPU does the work locally.",
    icon: (
      <svg viewBox="0 0 24 24" className="h-7 w-7 text-teal-mid" fill="none" stroke="currentColor" strokeWidth="1.75">
        <rect x="3" y="4" width="18" height="14" rx="2" />
        <path d="M8 20h8M12 18v2" />
        <path d="M7 9l3 3-3 3M13 15h4" />
      </svg>
    ),
  },
  {
    title: "Live raw metrics",
    description:
      "Track time to first token, tokens per second, and token counts as each response streams — the raw signals that matter.",
    icon: (
      <svg viewBox="0 0 24 24" className="h-7 w-7 text-teal-mid" fill="none" stroke="currentColor" strokeWidth="1.75">
        <path d="M4 19V5M4 19h16" />
        <path d="M8 15l3-4 3 2 4-6" />
        <circle cx="18" cy="7" r="1.5" fill="currentColor" stroke="none" />
      </svg>
    ),
  },
  {
    title: "Decision scoring",
    description:
      "Rule-based accept, review, or reject scores from latency, length, and format — transparent, deterministic, no black box.",
    icon: (
      <svg viewBox="0 0 24 24" className="h-7 w-7 text-teal-mid" fill="none" stroke="currentColor" strokeWidth="1.75">
        <path d="M12 2l2.4 7.4H22l-6 4.6 2.3 7L12 16.8 5.7 21l2.3-7-6-4.6h7.6L12 2z" />
      </svg>
    ),
  },
  {
    title: "Session history",
    description:
      "Persist chats and scores to PostgreSQL, then explore summaries, charts, and per-message detail on the dashboard.",
    icon: (
      <svg viewBox="0 0 24 24" className="h-7 w-7 text-teal-mid" fill="none" stroke="currentColor" strokeWidth="1.75">
        <path d="M4 19V5a1 1 0 011-1h14a1 1 0 011 1v14" />
        <path d="M8 17v-5M12 17V9M16 17v-3" />
      </svg>
    ),
  },
];

const steps = [
  {
    step: "1",
    title: "Sign in",
    description: "Create an account or log in to unlock the chat workspace and dashboard.",
  },
  {
    step: "2",
    title: "Load Gemma in your browser",
    description: "Pick a WebLLM model and initialize WebGPU — weights download once, then run locally.",
  },
  {
    step: "3",
    title: "Chat with live metrics",
    description: "Stream multi-turn responses while TTFT, tok/s, and token counts update in real time.",
  },
  {
    step: "4",
    title: "Review scores on the dashboard",
    description: "Browse session history, decision distributions, and per-message scoring breakdowns.",
  },
];

const techStack = ["Next.js", "Go", "WebLLM / MLC", "PostgreSQL", "Render", "Vercel"];

function scrollToAuth() {
  document.getElementById("auth")?.scrollIntoView({ behavior: "smooth" });
}

function MockMetricsPanel() {
  return (
    <GlowShell variant="card" className="mx-auto mt-12 max-w-lg p-5 sm:p-6">
      <div className="relative z-10">
        <p className="text-[13px] font-semibold uppercase tracking-wide text-ink-muted">
          Live preview
        </p>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
          <div>
            <p className="metric-value text-2xl">655</p>
            <p className="metric-label">TTFT ms</p>
          </div>
          <div>
            <p className="metric-value text-2xl">9.5</p>
            <p className="metric-label">tok/s</p>
          </div>
          <div className="col-span-2 sm:col-span-1 flex flex-col justify-center">
            <span className="inline-flex w-fit items-center rounded-full bg-green-100 px-2.5 py-0.5 text-[11px] font-semibold text-green-800">
              ACCEPT · 74
            </span>
            <p className="metric-label mt-1">Decision score</p>
          </div>
        </div>
        <svg
          viewBox="0 0 200 48"
          className="mt-4 h-12 w-full text-teal-mid"
          aria-hidden
        >
          <defs>
            <linearGradient id="sparkGrad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#7BBDE8" />
              <stop offset="100%" stopColor="#0A4174" />
            </linearGradient>
          </defs>
          <polyline
            fill="none"
            stroke="url(#sparkGrad)"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            points="0,38 25,32 50,28 75,22 100,18 125,20 150,12 175,8 200,4"
          />
          <polyline
            fill="url(#sparkGrad)"
            fillOpacity="0.15"
            stroke="none"
            points="0,48 0,38 25,32 50,28 75,22 100,18 125,20 150,12 175,8 200,4 200,48"
          />
        </svg>
      </div>
    </GlowShell>
  );
}

export default function LandingPage() {
  return (
    <div className="sky-landing min-h-screen font-system text-ink relative">
      <AmbientBackground />

      <header className="glass-header relative-z">
        <div className="glass-header-inner">
          <Link href="/" className="text-[17px] font-semibold text-ink">
            LLM Monitoring
          </Link>
          <nav className="flex items-center gap-6">
            <a href="#features" className="nav-link hidden sm:inline">
              Features
            </a>
            <a href="#how-it-works" className="nav-link hidden sm:inline">
              How it works
            </a>
            <button type="button" onClick={scrollToAuth} className="btn-primary text-[14px] py-2 px-4">
              Get started
            </button>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="relative-z flex min-h-[85vh] flex-col items-center justify-center px-6 pt-16 pb-24 text-center">
        <ScrollReveal className="max-w-3xl">
          <h1 className="hero-title text-balance mx-auto max-w-3xl">Watch your LLM think.</h1>
          <p className="mx-auto mt-5 max-w-xl text-[17px] leading-relaxed text-ink-body">
            In-browser Gemma inference with live raw metrics and decision scoring —
            see every token, every millisecond, every accept/review/reject verdict.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
            <button type="button" onClick={scrollToAuth} className="btn-primary">
              Get started
            </button>
            <Link href="/auth" className="btn-ghost">
              View dashboard demo
            </Link>
          </div>
          <MockMetricsPanel />
        </ScrollReveal>
      </section>

      {/* Features */}
      <section id="features" className="relative-z px-6 py-20 md:py-28">
        <div className="page-container">
          <ScrollReveal className="mb-12 text-center">
            <h2 className="section-title">Everything you need to monitor LLMs</h2>
            <p className="mx-auto mt-4 max-w-xl text-[17px] text-ink-body">
              From first token to final score — built for developers who want visibility, not guesswork.
            </p>
          </ScrollReveal>
          <div className="grid gap-5 sm:grid-cols-2">
            {features.map((feature) => (
              <ScrollReveal key={feature.title}>
                <FeatureCard
                  title={feature.title}
                  description={feature.description}
                  icon={feature.icon}
                />
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="relative-z section-band-deep px-6 py-20 md:py-28">
        <div className="page-container">
          <ScrollReveal className="mb-12 text-center">
            <h2 className="section-title">How it works</h2>
            <p className="mx-auto mt-4 max-w-xl text-[17px] text-ink-body">
              Four steps from sign-in to scored session review.
            </p>
          </ScrollReveal>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map((item) => (
              <ScrollReveal key={item.step}>
                <article className="glass-card-static p-5 h-full">
                  <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-white/50 text-sm font-bold text-ink">
                    {item.step}
                  </span>
                  <h3 className="mt-3 text-[18px] font-semibold text-ink">{item.title}</h3>
                  <p className="mt-2 text-[15px] leading-relaxed text-ink-body">{item.description}</p>
                </article>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </section>

      {/* Tech section */}
      <section className="relative-z section-band-navy px-6 py-16 md:py-20">
        <div className="page-container text-center">
          <ScrollReveal>
            <h2 className="section-title-light">Built with</h2>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              {techStack.map((tech) => (
                <span key={tech} className="glass-chip">
                  {tech}
                </span>
              ))}
            </div>
          </ScrollReveal>
        </div>
      </section>

      {/* Auth */}
      <section id="auth" className="relative-z px-6 py-20 md:py-28">
        <div className="page-container">
          <ScrollReveal className="flex flex-col items-center gap-10">
            <div className="max-w-md text-center">
              <h2 className="section-title">Start monitoring</h2>
              <p className="mt-4 text-[17px] text-ink-body">
                Create an account or sign in to open the chat workspace and dashboard.
              </p>
              <p className="mt-4 text-[15px] text-ink-muted">
                Prefer a direct link?{" "}
                <Link href="/auth" className="font-medium text-navy-mid underline underline-offset-2">
                  Open /auth
                </Link>
              </p>
            </div>
            <GlowShell variant="auth" className="w-full max-w-[420px]">
              <AuthForm title="Sign in" />
            </GlowShell>
          </ScrollReveal>
        </div>
      </section>

      <footer className="relative-z glass-footer py-4" aria-hidden />
    </div>
  );
}

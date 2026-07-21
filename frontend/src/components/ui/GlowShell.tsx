"use client";

import { useRef, type CSSProperties, type MouseEvent, type ReactNode } from "react";

type GlowShellProps = {
  children: ReactNode;
  className?: string;
  variant?: "card" | "auth" | "feature";
  defaultGlow?: number;
};

export function useGlowHandlers(defaultOpacity = 0) {
  const ref = useRef<HTMLDivElement>(null);

  function handleMouseMove(e: MouseEvent<HTMLDivElement>) {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top) / rect.height) * 100;
    el.style.setProperty("--glow-x", `${x}%`);
    el.style.setProperty("--glow-y", `${y}%`);
  }

  function handleMouseEnter() {
    ref.current?.style.setProperty("--glow-opacity", "1");
  }

  function handleMouseLeave() {
    ref.current?.style.setProperty("--glow-opacity", String(defaultOpacity));
  }

  return { ref, handleMouseMove, handleMouseEnter, handleMouseLeave };
}

export default function GlowShell({
  children,
  className = "",
  variant = "card",
  defaultGlow = 0,
}: GlowShellProps) {
  const { ref, handleMouseMove, handleMouseEnter, handleMouseLeave } =
    useGlowHandlers(defaultGlow);

  const variantClass =
    variant === "auth"
      ? "auth-glow-shell"
      : variant === "feature"
        ? "feature-card"
        : "glow-card";

  return (
    <div
      ref={ref}
      className={`${variantClass} ${className}`.trim()}
      onMouseMove={handleMouseMove}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      style={
        {
          "--glow-x": "50%",
          "--glow-y": "50%",
          "--glow-opacity": String(defaultGlow),
        } as CSSProperties
      }
    >
      {children}
    </div>
  );
}

"use client";

import { type ReactNode } from "react";
import GlowShell from "@/components/ui/GlowShell";

type FeatureCardProps = {
  title: string;
  description: string;
  icon: ReactNode;
};

export default function FeatureCard({ title, description, icon }: FeatureCardProps) {
  return (
    <GlowShell variant="feature" className="p-5 sm:p-6 h-full">
      <div className="relative z-10 flex flex-col gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/40">
          {icon}
        </div>
        <h3 className="text-lg font-semibold text-ink">{title}</h3>
        <p className="text-[15px] leading-relaxed text-ink-body">{description}</p>
      </div>
    </GlowShell>
  );
}

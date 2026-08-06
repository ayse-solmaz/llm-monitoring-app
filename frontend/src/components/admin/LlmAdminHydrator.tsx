"use client";

import { useEffect } from "react";
import { useLlmAdminStore } from "@/store/llmAdminStore";

/** Load persisted admin LLM settings from backend once per protected session. */
export default function LlmAdminHydrator() {
  const hydrated = useLlmAdminStore((s) => s.hydrated);
  const hydrateFromApi = useLlmAdminStore((s) => s.hydrateFromApi);

  useEffect(() => {
    if (!hydrated) {
      void hydrateFromApi();
    }
  }, [hydrated, hydrateFromApi]);

  return null;
}

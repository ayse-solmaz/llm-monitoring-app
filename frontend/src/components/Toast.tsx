"use client";

import { useEffect } from "react";
import { useToastStore } from "@/store/toastStore";

export default function Toast() {
  const { message, clearToast } = useToastStore();

  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(clearToast, 5000);
    return () => clearTimeout(timer);
  }, [message, clearToast]);

  if (!message) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-sm rounded border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 shadow-lg">
      <div className="flex items-start justify-between gap-3">
        <p>{message}</p>
        <button
          type="button"
          onClick={clearToast}
          className="text-red-700 hover:text-red-900"
          aria-label="Dismiss"
        >
          ×
        </button>
      </div>
    </div>
  );
}

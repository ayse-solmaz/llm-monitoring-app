type NavigatorWithGPU = Navigator & {
  gpu?: { requestAdapter: () => Promise<unknown | null> };
};

const WEBGPU_ADAPTER_TIMEOUT_MS = 5000;

function requestAdapterWithTimeout(
  gpu: NonNullable<NavigatorWithGPU["gpu"]>
): Promise<{ adapter: unknown | null; timedOut: boolean }> {
  return new Promise((resolve) => {
    let settled = false;

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      resolve({ adapter: null, timedOut: true });
    }, WEBGPU_ADAPTER_TIMEOUT_MS);

    gpu
      .requestAdapter()
      .then((adapter) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve({ adapter, timedOut: false });
      })
      .catch(() => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve({ adapter: null, timedOut: false });
      });
  });
}

export async function checkWebGPUSupport(): Promise<boolean> {
  if (typeof window === "undefined") return false;

  const gpu = (navigator as NavigatorWithGPU).gpu;
  if (!gpu) return false;

  const { adapter, timedOut } = await requestAdapterWithTimeout(gpu);
  if (timedOut) return true;
  return adapter !== null;
}

export const WEBGPU_FALLBACK_MESSAGE = {
  title: "WebGPU is not available",
  body: "Local inference requires WebGPU. Use a recent desktop browser with WebGPU enabled:",
  browsers: [
    "Google Chrome 113+ (recommended)",
    "Microsoft Edge 113+",
    "Other Chromium browsers with WebGPU enabled",
  ],
  hint: "Safari and Firefox may not work yet. In Chrome, enable GPU at chrome://settings/system. You can still try the standalone spike at /spike.",
};

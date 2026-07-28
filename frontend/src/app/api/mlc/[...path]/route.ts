import { NextRequest, NextResponse } from "next/server";

/**
 * Same-origin proxy: browser → /api/mlc/* → MLC gateway (tunnel or localhost).
 * Avoids browser CORS / Cloudflare quick-tunnel blocks from Vercel pages.
 *
 * Upstream: MLC_UPSTREAM (preferred) or NEXT_PUBLIC_MLC_URL or 127.0.0.1:8080
 *
 * Critical for chat SSE: return Response immediately with a ReadableStream that
 * flushes an early comment, then pipes upstream.body. Do NOT await json()/text().
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 600;

function upstreamBase(): string {
  const raw =
    process.env.MLC_UPSTREAM?.trim() ||
    process.env.NEXT_PUBLIC_MLC_URL?.trim() ||
    "http://127.0.0.1:8080";
  const match = raw.match(/https?:\/\/[^\s\\]+/i);
  return (match ? match[0] : "http://127.0.0.1:8080").replace(/\/$/, "");
}

function isEventStream(contentType: string | null): boolean {
  return !!contentType && contentType.toLowerCase().includes("text/event-stream");
}

async function proxy(req: NextRequest, pathParts: string[]) {
  const base = upstreamBase();
  const sub = pathParts.join("/");
  const search = req.nextUrl.search || "";
  const target = `${base}/${sub}${search}`;

  const headers: Record<string, string> = {};
  const contentType = req.headers.get("content-type");
  if (contentType) headers["Content-Type"] = contentType;
  const accept = req.headers.get("accept");
  // Prefer SSE when client omits Accept (browser chat fetch only sets Content-Type).
  if (accept) headers["Accept"] = accept;
  else if (req.method === "POST" && sub.includes("chat/completions")) {
    headers["Accept"] = "text/event-stream";
  }

  let body: string | undefined;
  if (req.method !== "GET" && req.method !== "HEAD" && req.method !== "OPTIONS") {
    body = await req.text();
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body,
      cache: "no-store",
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "upstream fetch failed";
    return NextResponse.json(
      {
        error: {
          message: `MLC proxy cannot reach ${base}: ${message}`,
          code: "upstream_unreachable",
        },
      },
      { status: 502 }
    );
  }

  const upstreamCt = upstream.headers.get("content-type");
  const stream = isEventStream(upstreamCt) || sub.includes("chat/completions");

  if (!stream || !upstream.body) {
    const outHeaders = new Headers();
    if (upstreamCt) outHeaders.set("Content-Type", upstreamCt);
    outHeaders.set("Cache-Control", "no-store");
    const xCache = upstream.headers.get("x-cache");
    if (xCache) outHeaders.set("X-Cache", xCache);
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: outHeaders,
    });
  }

  // Pipe SSE with an immediate comment so Next/clients flush headers before TTFT.
  const upstreamBody = upstream.body;
  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
  const writer = writable.getWriter();
  const encoder = new TextEncoder();

  (async () => {
    try {
      await writer.write(encoder.encode(": connected\n\n"));
      const reader = upstreamBody.getReader();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (value?.byteLength) await writer.write(value);
        }
      } finally {
        reader.releaseLock();
      }
    } catch {
      // Client abort / upstream reset — close below.
    } finally {
      try {
        await writer.close();
      } catch {
        // already closed
      }
    }
  })();

  const outHeaders = new Headers();
  outHeaders.set("Content-Type", "text/event-stream; charset=utf-8");
  outHeaders.set("Cache-Control", "no-cache, no-transform");
  outHeaders.set("Connection", "keep-alive");
  outHeaders.set("X-Accel-Buffering", "no");
  const xCache = upstream.headers.get("x-cache");
  if (xCache) outHeaders.set("X-Cache", xCache);

  return new Response(readable, {
    status: upstream.status,
    headers: outHeaders,
  });
}

type Ctx = { params: { path: string[] } };

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx.params.path || []);
}

export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx.params.path || []);
}

export async function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
    },
  });
}

import { NextRequest, NextResponse } from "next/server";

/**
 * Same-origin proxy: browser → /api/mlc/* → MLC gateway (tunnel or localhost).
 * Avoids browser CORS / Cloudflare quick-tunnel blocks from Vercel pages.
 *
 * Upstream: MLC_UPSTREAM (preferred) or NEXT_PUBLIC_MLC_URL or 127.0.0.1:8080
 */
export const runtime = "nodejs";
export const maxDuration = 300;

function upstreamBase(): string {
  const raw =
    process.env.MLC_UPSTREAM?.trim() ||
    process.env.NEXT_PUBLIC_MLC_URL?.trim() ||
    "http://127.0.0.1:8080";
  const match = raw.match(/https?:\/\/[^\s\\]+/i);
  return (match ? match[0] : "http://127.0.0.1:8080").replace(/\/$/, "");
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
  if (accept) headers["Accept"] = accept;

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

  const outHeaders = new Headers();
  const ct = upstream.headers.get("content-type");
  if (ct) outHeaders.set("Content-Type", ct);
  outHeaders.set("Cache-Control", "no-store");

  return new NextResponse(upstream.body, {
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

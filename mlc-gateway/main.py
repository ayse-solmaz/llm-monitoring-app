"""
MLC KPI Gateway (FastAPI)

Sits between the browser/loadtest and nginx→MLC. Forwards OpenAI-compatible
chat completions with stream=true, measures LLM KPIs, exposes /metrics for
Prometheus (pull model — does not push to Grafana).
"""

from __future__ import annotations

import json
import os
import time
from typing import AsyncIterator, Optional

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

MLC_UPSTREAM = os.getenv("MLC_UPSTREAM", "http://nginx:80").rstrip("/")
REQUEST_TIMEOUT = float(os.getenv("MLC_TIMEOUT_SECONDS", "600"))

REQUESTS = Counter(
    "llm_requests_total",
    "Total chat completion requests proxied to MLC",
    ["status"],
)
OUTPUT_TOKENS = Counter(
    "llm_output_tokens_total",
    "Total completion tokens observed from upstream usage or estimate",
)
INFLIGHT = Gauge(
    "llm_requests_inflight",
    "Chat completion requests currently in flight",
)
DURATION = Histogram(
    "llm_request_duration_seconds",
    "End-to-end chat completion latency",
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 180, 300, 600),
)
TTFT = Histogram(
    "llm_ttft_seconds",
    "Time to first streamed content token",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)
TOKENS_PER_SEC = Histogram(
    "llm_tokens_per_second",
    "Completion tokens / decode seconds (after first token)",
    buckets=(0.1, 0.5, 1, 2, 5, 10, 20, 50, 100),
)

app = FastAPI(title="MLC KPI Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3002",
        "https://llm-monitoring-app.vercel.app",
        "https://llm-monitoring-app-098765467890.vercel.app",
    ],
    allow_origin_regex=r"https://llm-monitoring-app.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_private_network_header(request: Request, call_next):
    # Chrome Private Network Access preflights (some browsers).
    if request.method == "OPTIONS" and request.headers.get(
        "access-control-request-private-network"
    ):
        response = Response(status_code=204)
        origin = request.headers.get("origin", "")
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response
    response = await call_next(request)
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "upstream": MLC_UPSTREAM}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.api_route("/v1/models", methods=["GET", "OPTIONS"])
async def models(request: Request):
    if request.method == "OPTIONS":
        return Response(status_code=204)
    async with httpx.AsyncClient(timeout=30.0) as client:
        upstream = await client.get(f"{MLC_UPSTREAM}/v1/models")
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "application/json"),
        )


def _estimate_tokens(text: str) -> int:
    words = [w for w in text.split() if w]
    return max(1, int(len(words) * 1.3)) if words else 0


async def _proxy_stream(
    body: bytes,
    headers: dict[str, str],
) -> tuple[AsyncIterator[bytes], dict]:
    """Return streaming iterator and a shared stats dict filled while iterating."""
    stats: dict = {
        "status": "ok",
        "ttft": None,
        "completion_tokens": 0,
        "prompt_tokens": 0,
        "started": time.perf_counter(),
        "first_token_at": None,
        "full_text": "",
    }

    async def gen() -> AsyncIterator[bytes]:
        INFLIGHT.inc()
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                async with client.stream(
                    "POST",
                    f"{MLC_UPSTREAM}/v1/chat/completions",
                    content=body,
                    headers=headers,
                ) as resp:
                    if resp.status_code >= 400:
                        stats["status"] = "error"
                        raw = await resp.aread()
                        # Prefer SSE error JSON over nginx HTML so browsers don't
                        # try to JSON.parse("<html>...").
                        text = raw.decode("utf-8", errors="replace")
                        if text.lstrip().startswith("<"):
                            err = {
                                "error": {
                                    "message": f"upstream HTTP {resp.status_code} (MLC busy or timed out)",
                                    "code": "upstream_error",
                                }
                            }
                            yield f"data: {json.dumps(err)}\n\n".encode("utf-8")
                            yield b"data: [DONE]\n\n"
                        else:
                            yield raw
                        return

                    buffer = ""
                    async for chunk in resp.aiter_text():
                        if not chunk:
                            continue
                        # Forward raw bytes to client immediately
                        yield chunk.encode("utf-8")

                        buffer += chunk
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if not data or data == "[DONE]":
                                continue
                            try:
                                parsed = json.loads(data)
                            except json.JSONDecodeError:
                                continue

                            delta = (
                                (parsed.get("choices") or [{}])[0]
                                .get("delta", {})
                                .get("content")
                            )
                            if delta:
                                if stats["first_token_at"] is None:
                                    stats["first_token_at"] = time.perf_counter()
                                    stats["ttft"] = (
                                        stats["first_token_at"] - stats["started"]
                                    )
                                stats["full_text"] += delta

                            usage = parsed.get("usage") or {}
                            if usage.get("completion_tokens"):
                                stats["completion_tokens"] = int(
                                    usage["completion_tokens"]
                                )
                            if usage.get("prompt_tokens"):
                                stats["prompt_tokens"] = int(usage["prompt_tokens"])
        except Exception:
            stats["status"] = "error"
            raise
        finally:
            INFLIGHT.dec()
            elapsed = time.perf_counter() - stats["started"]
            DURATION.observe(elapsed)
            REQUESTS.labels(status=stats["status"]).inc()

            if stats["ttft"] is not None:
                TTFT.observe(stats["ttft"])

            tokens = stats["completion_tokens"]
            if tokens <= 0 and stats["full_text"]:
                tokens = _estimate_tokens(stats["full_text"])
                stats["completion_tokens"] = tokens

            if tokens > 0:
                OUTPUT_TOKENS.inc(tokens)
                decode = elapsed - (stats["ttft"] or 0)
                if decode > 0:
                    TOKENS_PER_SEC.observe(tokens / decode)

    return gen, stats


@app.api_route("/v1/chat/completions", methods=["POST", "OPTIONS"])
async def chat_completions(request: Request):
    if request.method == "OPTIONS":
        return Response(status_code=204)

    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        REQUESTS.labels(status="error").inc()
        return JSONResponse(
            {"error": {"message": "invalid JSON body", "code": "bad_request"}},
            status_code=400,
        )

    # Drop non-OpenAI fields so MLC does not reject the body.
    payload.pop("adapter_id", None)
    # Some MLC builds choke on stream_options — strip unless client sent it.
    # (KPI path still works: we measure TTFT from SSE when stream=true.)
    want_stream = bool(payload.get("stream", True))
    payload["stream"] = want_stream
    if want_stream and "stream_options" not in payload:
        payload["stream_options"] = {"include_usage": True}
    if not want_stream:
        payload.pop("stream_options", None)

    body = json.dumps(payload).encode("utf-8")

    # Non-stream: buffer full upstream JSON (clearer for CPU fallback / curl).
    if not want_stream:
        INFLIGHT.inc()
        started = time.perf_counter()
        status_label = "ok"
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                upstream = await client.post(
                    f"{MLC_UPSTREAM}/v1/chat/completions",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )
            if upstream.status_code >= 400:
                status_label = "error"
                text = upstream.text
                # nginx HTML errors → JSON for the browser
                if text.lstrip().startswith("<"):
                    return JSONResponse(
                        {
                            "error": {
                                "message": f"upstream HTTP {upstream.status_code} (HTML error page — MLC busy/timeout)",
                                "code": "upstream_error",
                            }
                        },
                        status_code=502,
                    )
                return Response(
                    content=upstream.content,
                    status_code=upstream.status_code,
                    media_type=upstream.headers.get(
                        "content-type", "application/json"
                    ),
                )
            return Response(
                content=upstream.content,
                status_code=upstream.status_code,
                media_type=upstream.headers.get(
                    "content-type", "application/json"
                ),
            )
        except Exception as exc:
            status_label = "error"
            return JSONResponse(
                {
                    "error": {
                        "message": f"upstream failed: {exc}",
                        "code": "upstream_error",
                    }
                },
                status_code=502,
            )
        finally:
            INFLIGHT.dec()
            DURATION.observe(time.perf_counter() - started)
            REQUESTS.labels(status=status_label).inc()

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    stream_fn, _stats = await _proxy_stream(body, headers)
    return StreamingResponse(stream_fn(), media_type="text/event-stream")

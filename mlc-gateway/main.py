"""
MLC KPI Gateway (FastAPI)

Sits between the browser/loadtest and nginx→MLC. Forwards OpenAI-compatible
chat completions with stream=true, measures LLM KPIs, exposes /metrics for
Prometheus (pull model — does not push to Grafana).

L2: MAX_INFLIGHT semaphore queue, startup prewarm, /healthz ready, LRU cache.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
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
MAX_INFLIGHT = max(1, int(os.getenv("MAX_INFLIGHT", "1")))
CACHE_MAX = max(0, int(os.getenv("CACHE_MAX", "64")))
QUEUE_SSE = os.getenv("QUEUE_SSE", "1").strip().lower() not in ("0", "false", "no")
# Prewarm retries while MLC is still loading (502s); background task after startup.
PREWARM_INTERVAL = float(os.getenv("PREWARM_INTERVAL_SECONDS", "7"))
PREWARM_MAX_WAIT = float(os.getenv("PREWARM_MAX_WAIT_SECONDS", "300"))
PREWARM_TIMEOUT = float(os.getenv("PREWARM_TIMEOUT_SECONDS", "60"))

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

_inflight_sem: Optional[asyncio.Semaphore] = None
_ready = False
_cache: OrderedDict[str, str] = OrderedDict()


def _sem() -> asyncio.Semaphore:
    assert _inflight_sem is not None, "semaphore not initialized"
    return _inflight_sem


def _cache_key(payload: dict) -> str:
    """Stable key from messages + model + temperature (demo repeat Qs)."""
    blob = json.dumps(
        {
            "messages": payload.get("messages") or [],
            "model": payload.get("model") or "",
            "temperature": payload.get("temperature", 1.0),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> Optional[str]:
    if CACHE_MAX <= 0 or key not in _cache:
        return None
    _cache.move_to_end(key)
    return _cache[key]


def _cache_put(key: str, value: str) -> None:
    if CACHE_MAX <= 0 or not value:
        return
    if key in _cache:
        _cache.move_to_end(key)
    _cache[key] = value
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)


async def _acquire_slot() -> None:
    """Block until an inflight slot is free (no SSE)."""
    await _sem().acquire()


async def _acquire_slot_streaming() -> AsyncIterator[bytes]:
    """
    Acquire an inflight slot, yielding optional SSE event:queue while waiting
    so the client sees a queue instead of an upstream HTML 502.
    Caller MUST release the semaphore in a finally block.
    """
    while True:
        try:
            await asyncio.wait_for(_sem().acquire(), timeout=0.5)
            return
        except asyncio.TimeoutError:
            if QUEUE_SSE:
                payload = json.dumps(
                    {"status": "waiting", "max_inflight": MAX_INFLIGHT}
                )
                yield f"event: queue\ndata: {payload}\n\n".encode("utf-8")


async def _prewarm_once() -> bool:
    """One-token non-stream request; returns True if upstream accepted it."""
    body = {
        "model": "/app/model",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=PREWARM_TIMEOUT) as client:
            resp = await client.post(
                f"{MLC_UPSTREAM}/v1/chat/completions",
                json=body,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            if resp.status_code < 400:
                return True
            print(f"prewarm: upstream HTTP {resp.status_code}", flush=True)
            return False
    except Exception as exc:
        print(f"prewarm: failed — {exc}", flush=True)
        return False


async def _prewarm_loop() -> None:
    """
    Retry prewarm with fixed backoff until success or PREWARM_MAX_WAIT.
    MLC often returns 502 while still loading; a single attempt left ready=false forever.
    """
    global _ready
    deadline = time.monotonic() + PREWARM_MAX_WAIT
    attempt = 0
    while True:
        attempt += 1
        ok = await _prewarm_once()
        if ok:
            _ready = True
            print(f"prewarm: ready (attempt {attempt})", flush=True)
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _ready = False
            print(
                f"prewarm: giving up after {attempt} attempt(s) "
                f"(~{PREWARM_MAX_WAIT:.0f}s); ready=false",
                flush=True,
            )
            return
        sleep_for = min(PREWARM_INTERVAL, remaining)
        print(
            f"prewarm: retry in {sleep_for:.0f}s "
            f"(attempt {attempt}, {remaining:.0f}s left)",
            flush=True,
        )
        await asyncio.sleep(sleep_for)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _inflight_sem
    _inflight_sem = asyncio.Semaphore(MAX_INFLIGHT)
    # Do not block startup on MLC — retry in background until ready or timeout.
    task = asyncio.create_task(_prewarm_loop(), name="prewarm")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="MLC KPI Gateway", version="1.1.0", lifespan=lifespan)

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
    return {
        "status": "ok",
        "upstream": MLC_UPSTREAM,
        "ready": _ready,
        "max_inflight": MAX_INFLIGHT,
    }


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


def _cached_completion_json(text: str) -> bytes:
    return json.dumps(
        {
            "id": "cached",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": _estimate_tokens(text),
                "total_tokens": _estimate_tokens(text),
            },
        }
    ).encode("utf-8")


async def _replay_cached_sse(text: str) -> AsyncIterator[bytes]:
    chunk = {
        "id": "cached",
        "object": "chat.completion.chunk",
        "choices": [
            {"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}
        ],
    }
    yield f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
    done = {
        "id": "cached",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(done)}\n\n".encode("utf-8")
    yield b"data: [DONE]\n\n"


async def _proxy_stream(
    body: bytes,
    headers: dict[str, str],
    cache_key: Optional[str] = None,
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
        acquired = False
        try:
            # Flush an SSE comment immediately so proxies (Next /api/mlc) send
            # response headers before MLC TTFT (CPU can be minutes).
            yield b": gateway-open\n\n"

            # Queue behind MAX_INFLIGHT; emit event:queue while waiting.
            async for qchunk in _acquire_slot_streaming():
                yield qchunk
            acquired = True

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

                if stats["status"] == "ok" and cache_key and stats["full_text"]:
                    _cache_put(cache_key, stats["full_text"])
        finally:
            if acquired:
                _sem().release()

    return gen, stats


def _normalize_payload(payload: dict) -> dict:
    """Drop non-OpenAI fields, cap tokens, trim messages (CPU TTFT)."""
    payload.pop("adapter_id", None)
    payload.pop("stream_options", None)

    try:
        mt = int(payload.get("max_tokens") or 16)
    except (TypeError, ValueError):
        mt = 16
    payload["max_tokens"] = max(1, min(mt, 24))

    msgs = payload.get("messages")
    if isinstance(msgs, list):
        trimmed = []
        for m in msgs[-3:]:  # keep at most last 3 turns
            if not isinstance(m, dict):
                continue
            content = m.get("content")
            if isinstance(content, str) and len(content) > 350:
                content = content[:350]
            role = m.get("role") or "user"
            if role not in ("user", "assistant", "system"):
                role = "user"
            # Gemma-IT: avoid system role — fold into user if needed
            if role == "system" and isinstance(content, str):
                trimmed.append({"role": "user", "content": content[:200]})
            else:
                trimmed.append(
                    {
                        "role": role,
                        "content": content if isinstance(content, str) else "",
                    }
                )
        payload["messages"] = trimmed
    return payload


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

    payload = _normalize_payload(payload)
    want_stream = bool(payload.get("stream", True))
    payload["stream"] = want_stream

    key = _cache_key(payload)
    cached = _cache_get(key)
    if cached is not None:
        if want_stream:
            return StreamingResponse(
                _replay_cached_sse(cached),
                media_type="text/event-stream",
                headers={
                    "X-Cache": "HIT",
                    "Cache-Control": "no-cache, no-transform",
                    "X-Accel-Buffering": "no",
                },
            )
        return Response(
            content=_cached_completion_json(cached),
            status_code=200,
            media_type="application/json",
            headers={"X-Cache": "HIT", "Cache-Control": "no-store"},
        )

    body = json.dumps(payload).encode("utf-8")

    # Non-stream: buffer full upstream JSON (clearer for CPU fallback / curl).
    if not want_stream:
        # Wait for a free slot (no SSE — client expects one JSON body).
        await _acquire_slot()

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
                        headers={"X-Cache": "MISS"},
                    )
                return Response(
                    content=upstream.content,
                    status_code=upstream.status_code,
                    media_type=upstream.headers.get(
                        "content-type", "application/json"
                    ),
                    headers={"X-Cache": "MISS"},
                )

            # Cache assistant text for demo repeats.
            try:
                parsed = upstream.json()
                content = (
                    (parsed.get("choices") or [{}])[0]
                    .get("message", {})
                    .get("content")
                )
                if isinstance(content, str) and content:
                    _cache_put(key, content)
            except Exception:
                pass

            return Response(
                content=upstream.content,
                status_code=upstream.status_code,
                media_type=upstream.headers.get(
                    "content-type", "application/json"
                ),
                headers={"X-Cache": "MISS"},
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
                headers={"X-Cache": "MISS"},
            )
        finally:
            _sem().release()
            INFLIGHT.dec()
            DURATION.observe(time.perf_counter() - started)
            REQUESTS.labels(status=status_label).inc()

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    stream_fn, _stats = await _proxy_stream(body, headers, cache_key=key)
    return StreamingResponse(
        stream_fn(),
        media_type="text/event-stream",
        headers={
            "X-Cache": "MISS",
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

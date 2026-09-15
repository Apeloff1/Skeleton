"""
security.py — Lightweight security middleware for the FastAPI app.

Provides three independent layers, each is opt-in via wire-up in server.py:

  1. RateLimitMiddleware       — Per-IP+route token bucket (in-memory)
  2. AuditMiddleware           — Bounded ring buffer of every /api/* request
  3. SizeLimitMiddleware       — Hard cap on inbound request body
  4. safe_relative_path()      — Path-traversal protection helper

The audit buffer is also exposed via /api/security/audit (see telemetry router).
None of these layers persist data outside RAM — they're zero-overhead at idle.
"""
from __future__ import annotations
import os
import time
import asyncio
from collections import deque
from typing import Deque, Dict, Tuple
from pathlib import Path

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


# ─────────────────────────────────────────────────────────────────
# Rate limiter — token bucket per (ip, route_prefix)
# ─────────────────────────────────────────────────────────────────
class _Bucket:
    __slots__ = ("tokens", "last_refill")

    def __init__(self, tokens: float, last_refill: float):
        self.tokens = tokens
        self.last_refill = last_refill


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP, per-route-prefix token bucket. State is module-level so all
    middleware instances share it (FastAPI may construct multiple)."""

    # Shared across all instances (module-level singletons)
    _buckets: Dict[Tuple[str, str], _Bucket] = {}
    _lock = asyncio.Lock()
    _rps: float = 2.0
    _burst: int = 120

    def __init__(
        self,
        app,
        rps: float | None = None,
        burst: int | None = None,
        prefix: str = "/api",
    ):
        super().__init__(app)
        RateLimitMiddleware._rps = rps or float(os.environ.get("CODEDOCK_RATE_LIMIT_RPS", "2"))
        RateLimitMiddleware._burst = burst or int(os.environ.get("CODEDOCK_RATE_LIMIT_BURST", "120"))
        self.prefix = prefix
        self._whitelist = (
            "/api/health",
            "/api/binary/download",
            "/api/binary/inspect",         # cheap GET, called by inspector UI
            "/api/binary/toolchain",       # cheap GET
            "/api/binary/list",            # cheap GET
            "/api/security/",              # security endpoints exempt
            "/api/telemetry/event",        # ingest endpoint exempt (batched)
            "/api/telemetry/batch",
        )

    def _key(self, request: Request) -> Tuple[str, str]:
        ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not ip:
            ip = request.client.host if request.client else "unknown"
        parts = request.url.path.split("/", 4)
        route = "/".join(parts[:4]) if len(parts) >= 4 else request.url.path
        return ip, route

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith(self.prefix) or any(path.startswith(w) for w in self._whitelist):
            return await call_next(request)

        now = time.time()
        ip, route = self._key(request)
        async with RateLimitMiddleware._lock:
            bucket = RateLimitMiddleware._buckets.get((ip, route))
            if bucket is None:
                bucket = _Bucket(tokens=float(RateLimitMiddleware._burst), last_refill=now)
                RateLimitMiddleware._buckets[(ip, route)] = bucket
            elapsed = now - bucket.last_refill
            bucket.tokens = min(float(RateLimitMiddleware._burst), bucket.tokens + elapsed * RateLimitMiddleware._rps)
            bucket.last_refill = now
            if bucket.tokens < 1.0:
                retry_after = max(1, int((1.0 - bucket.tokens) / max(RateLimitMiddleware._rps, 0.01)))
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limited",
                        "detail": f"too many requests on {route}",
                        "retry_after_seconds": retry_after,
                        "burst": RateLimitMiddleware._burst,
                        "rps": RateLimitMiddleware._rps,
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.tokens -= 1.0

        return await call_next(request)

    @classmethod
    def snapshot(cls) -> dict:
        """Read-only view of current bucket state."""
        return {
            "rps": cls._rps,
            "burst": cls._burst,
            "active_buckets": len(cls._buckets),
            "top": [
                {"ip": k[0], "route": k[1], "tokens_remaining": round(v.tokens, 2)}
                for k, v in sorted(cls._buckets.items(), key=lambda kv: kv[1].tokens)[:20]
            ],
        }


# ─────────────────────────────────────────────────────────────────
# Audit — bounded ring buffer of every /api/* request
# ─────────────────────────────────────────────────────────────────
class AuditMiddleware(BaseHTTPMiddleware):
    """Records the last N /api/* requests in a ring buffer (module-level
    shared state so all middleware instances contribute to the same log)."""

    # Module-level shared buffer
    _buf: Deque[dict] = deque(maxlen=5000)
    _max_entries: int = 5000

    def __init__(self, app, max_entries: int = 5000):
        super().__init__(app)
        if max_entries > AuditMiddleware._max_entries:
            AuditMiddleware._max_entries = max_entries
            # Replace deque preserving existing entries
            old = list(AuditMiddleware._buf)
            AuditMiddleware._buf = deque(old, maxlen=max_entries)

    async def dispatch(self, request: Request, call_next):
        if not _matches_api_boundary(request.url.path):
            return await call_next(request)

        start = time.perf_counter()
        # Audit data must not trust attacker-controlled forwarding headers. The
        # canonical proxy-aware middleware records the resolved client identity;
        # this legacy audit layer uses the direct peer as a safe fallback.
        ip = request.client.host if request.client else "unknown"
        ua = request.headers.get("user-agent", "")[:200]
        rid = getattr(request.state, "request_id", None) or os.urandom(4).hex()

        # Never parse an untrusted Content-Length unless it is a small decimal.
        # The raw SizeLimitMiddleware performs authoritative framing validation
        # downstream; audit telemetry must not raise before that guard can reject
        # malformed, duplicated, or absurd declared lengths.
        raw_content_length = request.headers.get("content-length", "")
        if (
            raw_content_length.isascii()
            and raw_content_length.isdigit()
            and len(raw_content_length) <= 20
        ):
            body_size = int(raw_content_length, 10)
        else:
            body_size = 0

        error = None
        status = 0
        response: Response | None = None
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            status = 500
            raise
        finally:
            dur_ms = round((time.perf_counter() - start) * 1000, 2)
            AuditMiddleware._buf.append({
                "ts":          time.time(),
                "method":      request.method,
                "path":        request.url.path,
                "status":      status,
                "duration_ms": dur_ms,
                "ip":          ip,
                "ua":          ua,
                "rid":         rid,
                "req_bytes":   body_size,
                "error":       error,
            })
        return response

    @classmethod
    def snapshot(cls, limit: int = 200, since_ts: float | None = None) -> dict:
        rows = list(cls._buf)
        if since_ts:
            rows = [r for r in rows if r["ts"] >= since_ts]
        rows = rows[-limit:]
        return {
            "count": len(rows),
            "buffer_capacity": cls._max_entries,
            "buffer_size_now": len(cls._buf),
            "entries": rows,
        }

    @classmethod
    def summary(cls) -> dict:
        if not cls._buf:
            return {"empty": True}
        statuses: Dict[int, int] = {}
        methods: Dict[str, int] = {}
        path_counts: Dict[str, int] = {}
        path_times: Dict[str, list] = {}
        errors = 0
        total_ms = 0.0
        for r in cls._buf:
            statuses[r["status"]] = statuses.get(r["status"], 0) + 1
            methods[r["method"]] = methods.get(r["method"], 0) + 1
            p = r["path"]
            path_counts[p] = path_counts.get(p, 0) + 1
            path_times.setdefault(p, []).append(r["duration_ms"])
            if r["status"] >= 500 or r["error"]:
                errors += 1
            total_ms += r["duration_ms"]
        top_paths = sorted(path_counts.items(), key=lambda kv: -kv[1])[:15]
        slowest = sorted(
            [(p, max(t), sum(t) / len(t)) for p, t in path_times.items()],
            key=lambda x: -x[1],
        )[:10]
        return {
            "total_requests": len(cls._buf),
            "errors":         errors,
            "error_rate":     round(errors / max(len(cls._buf), 1), 4),
            "avg_ms":         round(total_ms / len(cls._buf), 2),
            "statuses":       dict(sorted(statuses.items())),
            "methods":        methods,
            "top_paths":      [{"path": p, "count": c} for p, c in top_paths],
            "slowest":        [
                {"path": p, "p_max_ms": round(mx, 1), "p_avg_ms": round(av, 1)}
                for p, mx, av in slowest
            ],
        }


# ─────────────────────────────────────────────────────────────────
# Body-size cap
# ─────────────────────────────────────────────────────────────────
def _matches_api_boundary(path: str) -> bool:
    """Match /api itself or a true child route, never /apiary-style lookalikes."""
    return path == "/api" or path.startswith("/api/")


class SizeLimitMiddleware:
    """Fail closed on malformed request framing and oversized API bodies.

    The middleware is a raw ASGI boundary rather than BaseHTTPMiddleware so it
    can count every streamed body chunk before application code runs. Bodies are
    buffered only after reserving space from a bounded aggregate in-flight
    budget, then replayed verbatim to the downstream application.
    """

    def __init__(
        self,
        app,
        max_mb: int | None = None,
        max_inflight_mb: int | None = None,
    ):
        self.app = app
        configured_mb = max_mb if max_mb is not None else int(
            os.environ.get("CODEDOCK_MAX_BODY_MB", "25")
        )
        configured_inflight_mb = (
            max_inflight_mb
            if max_inflight_mb is not None
            else int(os.environ.get("CODEDOCK_MAX_INFLIGHT_BODY_MB", "128"))
        )
        if configured_mb <= 0:
            raise ValueError("maximum body size must be positive")
        if configured_inflight_mb <= 0:
            raise ValueError("maximum in-flight body budget must be positive")

        self.max_bytes = int(configured_mb) * 1024 * 1024
        self.max_inflight_bytes = int(configured_inflight_mb) * 1024 * 1024
        self._inflight_body_bytes = 0
        self._inflight_lock = asyncio.Lock()

    async def _reserve_body_bytes(self, amount: int) -> bool:
        if amount <= 0:
            return True
        async with self._inflight_lock:
            if amount > self.max_inflight_bytes - self._inflight_body_bytes:
                return False
            self._inflight_body_bytes += amount
            return True

    async def _release_body_bytes(self, amount: int) -> None:
        if amount <= 0:
            return
        async with self._inflight_lock:
            self._inflight_body_bytes = max(0, self._inflight_body_bytes - amount)

    async def _reject(self, scope, receive, send, *, status_code: int, content: dict, headers=None):
        response = JSONResponse(status_code=status_code, content=content, headers=headers)
        await response(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or "/"
        if not _matches_api_boundary(path):
            await self.app(scope, receive, send)
            return

        raw_headers = list(scope.get("headers") or [])
        content_lengths = [
            value.decode("latin-1").strip(" \t")
            for key, value in raw_headers
            if key.lower() == b"content-length"
        ]
        transfer_encodings = [
            value.decode("latin-1").strip(" \t")
            for key, value in raw_headers
            if key.lower() == b"transfer-encoding"
        ]

        if len(content_lengths) > 1 or len(transfer_encodings) > 1:
            await self._reject(
                scope,
                receive,
                send,
                status_code=400,
                content={"error": "invalid_request_framing"},
            )
            return
        if content_lengths and transfer_encodings:
            await self._reject(
                scope,
                receive,
                send,
                status_code=400,
                content={"error": "invalid_request_framing"},
            )
            return

        declared: int | None = None
        if content_lengths:
            raw_declared = content_lengths[0]
            if not raw_declared.isascii() or not raw_declared.isdigit():
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    content={"error": "invalid_content_length"},
                )
                return

            normalized_declared = raw_declared.lstrip("0") or "0"
            limit_text = str(self.max_bytes)
            if len(normalized_declared) > len(limit_text) or (
                len(normalized_declared) == len(limit_text)
                and normalized_declared > limit_text
            ):
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=413,
                    content={
                        "error": "payload_too_large",
                        "detail": f"body exceeds {self.max_bytes // 1024 // 1024} MB",
                        "limit_bytes": self.max_bytes,
                        "got_bytes_at_least": self.max_bytes + 1,
                    },
                )
                return
            declared = int(normalized_declared, 10)

        buffered: list[dict] = []
        seen = 0
        reserved = 0
        try:
            while True:
                message = await receive()
                message_type = message.get("type")
                if message_type == "http.disconnect":
                    return
                if message_type != "http.request":
                    await self._reject(
                        scope,
                        receive,
                        send,
                        status_code=400,
                        content={"error": "invalid_request_body_stream"},
                    )
                    return

                body = message.get("body") or b""
                if not isinstance(body, (bytes, bytearray)):
                    await self._reject(
                        scope,
                        receive,
                        send,
                        status_code=400,
                        content={"error": "invalid_request_body_stream"},
                    )
                    return
                chunk_size = len(body)

                if seen + chunk_size > self.max_bytes:
                    await self._reject(
                        scope,
                        receive,
                        send,
                        status_code=413,
                        content={
                            "error": "payload_too_large",
                            "detail": f"body exceeds {self.max_bytes // 1024 // 1024} MB",
                            "limit_bytes": self.max_bytes,
                            "got_bytes": seen + chunk_size,
                        },
                    )
                    return

                if not await self._reserve_body_bytes(chunk_size):
                    await self._reject(
                        scope,
                        receive,
                        send,
                        status_code=503,
                        content={
                            "error": "body_capacity_exhausted",
                            "detail": "in-flight request body budget exhausted",
                            "limit_bytes": self.max_inflight_bytes,
                        },
                        headers={"Retry-After": "1"},
                    )
                    return

                reserved += chunk_size
                seen += chunk_size
                buffered.append(
                    {
                        **message,
                        "body": bytes(body),
                    }
                )
                if not message.get("more_body", False):
                    break

            if declared is not None and seen != declared:
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    content={"error": "invalid_content_length"},
                )
                return

            index = 0

            async def replay_receive():
                nonlocal index
                if index < len(buffered):
                    message = buffered[index]
                    index += 1
                    return message
                return {"type": "http.request", "body": b"", "more_body": False}

            await self.app(scope, replay_receive, send)
        finally:
            await self._release_body_bytes(reserved)


# ─────────────────────────────────────────────────────────────────
# Path traversal helper
# ─────────────────────────────────────────────────────────────────
def safe_relative_path(base: Path | str, candidate: str) -> Path:
    """
    Resolve `candidate` (a user-supplied filename / relative path) against
    `base`, raising ValueError if the result escapes `base`. Use this
    anywhere a path-like value comes from JSON / query params.

        safe_relative_path("/app/uploads", request_json["filename"])
    """
    base = Path(base).resolve()
    candidate = candidate.replace("\\", "/")
    if candidate.startswith("/"):
        candidate = candidate.lstrip("/")
    target = (base / candidate).resolve()
    if base != target and base not in target.parents:
        raise ValueError(f"path traversal blocked: {candidate}")
    return target


# Singletons exposed so server.py and the telemetry router can reach them.
_audit_mw: AuditMiddleware | None = None
_rate_mw:  RateLimitMiddleware | None = None


def register(audit: AuditMiddleware, rate: RateLimitMiddleware) -> None:
    global _audit_mw, _rate_mw
    _audit_mw = audit
    _rate_mw = rate


def get_audit() -> AuditMiddleware | None:
    return _audit_mw


def get_rate() -> RateLimitMiddleware | None:
    return _rate_mw

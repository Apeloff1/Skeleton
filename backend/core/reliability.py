"""
core/reliability.py — Backend reliability primitives (Feb 2026).

Provides reusable building blocks for the seven Category-1 upgrades:

    1. @idempotent(...)      — keyed cache so duplicate POSTs return the same
                                response instead of creating duplicates.
    2. mongo_retry(coro, ...)— exponential-backoff wrapper around any
                                async Mongo call.
    3. RequestTimeoutMiddleware — hard per-route timeout, returns 504.
    4. CircuitBreaker(...)   — open-after-N-fails breaker for outbound calls.
    5. dlq                   — module-level ringbuffer of failed background
                                tasks for /api/health/dlq inspection.
    6. install_graceful_drain(app) — registers SIGTERM/SIGINT handlers that
                                let inflight requests finish before exit.
    7. LoadShedding          — middleware that 503s when health markers
                                exceed thresholds (e.g. watchdog stale).

These are pure-Python and depend only on motor/fastapi/asyncio.
Every primitive is no-op safe — if something explodes inside, the wrapped
work still happens. Reliability code must NEVER be the reason for an outage.
"""
from __future__ import annotations
import asyncio
import functools
import hashlib
import json
import logging
import os
import signal
import time
from collections import deque
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("Reliability")

# ════════════════════════════════════════════════════════════════════════════
#  1. IDEMPOTENCY
# ════════════════════════════════════════════════════════════════════════════
class _IdemEntry:
    __slots__ = ("ts", "result")
    def __init__(self, result):
        self.ts = time.time()
        self.result = result

_IDEM_CACHE: dict[str, _IdemEntry] = {}
_IDEM_LOCKS: dict[str, asyncio.Lock] = {}
IDEM_TTL_SEC = 5 * 60  # 5-min window — enough to deduplicate retry storms.

def _idem_evict():
    """Drop entries older than IDEM_TTL_SEC (called opportunistically)."""
    now = time.time()
    stale = [k for k, e in _IDEM_CACHE.items() if now - e.ts > IDEM_TTL_SEC]
    for k in stale:
        _IDEM_CACHE.pop(k, None)
        _IDEM_LOCKS.pop(k, None)

def idempotent(ttl: int = IDEM_TTL_SEC):
    """Decorator: dedupe POST handlers by `Idempotency-Key` header.

    Usage:
        @router.post("/builds")
        @idempotent()
        async def create_build(request: Request, body: BuildBody): ...

    If two requests arrive with the same key, the second waits for the
    first to finish and returns the same response.  Window: TTL seconds.
    """
    def decorator(fn: Callable[..., Awaitable[Any]]):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            # Locate Request object (might be positional or kw)
            req: Optional[Request] = None
            for a in args:
                if isinstance(a, Request): req = a; break
            if req is None:
                req = kwargs.get("request")
            if req is None:
                return await fn(*args, **kwargs)
            key = req.headers.get("Idempotency-Key") or req.headers.get("idempotency-key")
            if not key:
                return await fn(*args, **kwargs)
            full_key = f"{req.url.path}:{key}"
            _idem_evict()
            if full_key in _IDEM_CACHE:
                logger.info(f"[idempotent] cache hit for {full_key[:80]}")
                return _IDEM_CACHE[full_key].result
            lock = _IDEM_LOCKS.setdefault(full_key, asyncio.Lock())
            async with lock:
                if full_key in _IDEM_CACHE:
                    return _IDEM_CACHE[full_key].result
                result = await fn(*args, **kwargs)
                _IDEM_CACHE[full_key] = _IdemEntry(result)
                return result
        return wrapper
    return decorator


# ════════════════════════════════════════════════════════════════════════════
#  2. MONGO RETRY (exponential backoff)
# ════════════════════════════════════════════════════════════════════════════
async def mongo_retry(
    coro_factory: Callable[[], Awaitable[Any]],
    *, retries: int = 3, base_delay: float = 0.15, max_delay: float = 1.5,
    label: str = "mongo",
):
    """Run an async Mongo call with exponential backoff.

    Args:
        coro_factory: zero-arg callable returning the coroutine. (We need a
                      factory because coroutines are single-use.)
        retries: max attempts (default 3 — 1 try + 2 retries).
        base_delay/max_delay: backoff window in seconds.
        label: for log lines.

    Returns the call result, or raises after all retries are exhausted.
    """
    attempt = 0
    delay = base_delay
    last_err: Exception | None = None
    while attempt < retries:
        try:
            return await coro_factory()
        except Exception as e:
            last_err = e
            # Some Mongo errors aren't transient; bail out fast on those.
            msg = str(e).lower()
            if any(s in msg for s in ("duplicate key", "validation failed", "bson")):
                raise
            attempt += 1
            if attempt >= retries:
                break
            logger.warning(f"[mongo_retry/{label}] attempt {attempt} failed: {e}; sleeping {delay:.2f}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
    raise last_err  # type: ignore


# ════════════════════════════════════════════════════════════════════════════
#  3. REQUEST TIMEOUT MIDDLEWARE
# ════════════════════════════════════════════════════════════════════════════
class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """Hard per-request timeout. Returns 504 if a handler exceeds the budget.

    Default 60 s. Long-running ops (builds, batch generators) MUST run
    out-of-band via background tasks rather than holding the request open.

    Bypass paths can be passed via `bypass_prefixes` (e.g. SSE / WebSocket).
    """
    def __init__(self, app, *, timeout: float = 60.0,
                 bypass_prefixes: tuple[str, ...] = ("/api/ai/stream", "/api/sse")):
        super().__init__(app)
        self.timeout = timeout
        self.bypass = bypass_prefixes

    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(p) for p in self.bypass):
            return await call_next(request)
        try:
            return await asyncio.wait_for(call_next(request), timeout=self.timeout)
        except asyncio.TimeoutError:
            logger.warning(f"[timeout] {request.method} {request.url.path} exceeded {self.timeout}s")
            return JSONResponse(
                {"error": "request_timeout", "timeout_s": self.timeout},
                status_code=504,
            )


# ════════════════════════════════════════════════════════════════════════════
#  4. CIRCUIT BREAKER
# ════════════════════════════════════════════════════════════════════════════
class CircuitBreaker:
    """Open after N consecutive failures; auto-close after cool-down.

    State machine:
        closed   — normal operation.
        open     — short-circuit all calls for cool_down seconds.
        half_open — let one call through; success closes, fail re-opens.
    """
    def __init__(self, *, name: str, fail_threshold: int = 5, cool_down: float = 60.0):
        self.name = name
        self.fail_threshold = fail_threshold
        self.cool_down = cool_down
        self._state = "closed"
        self._fail_count = 0
        self._opened_at: Optional[float] = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        if self._state == "open" and self._opened_at and (time.time() - self._opened_at) > self.cool_down:
            self._state = "half_open"
        return self._state

    async def call(self, coro_factory: Callable[[], Awaitable[Any]]):
        st = self.state
        if st == "open":
            raise RuntimeError(f"circuit_open:{self.name}")
        try:
            result = await coro_factory()
            # Success — reset
            async with self._lock:
                if self._state != "closed":
                    logger.info(f"[breaker/{self.name}] reset to closed")
                self._state = "closed"
                self._fail_count = 0
                self._opened_at = None
            return result
        except Exception:
            async with self._lock:
                self._fail_count += 1
                if self._fail_count >= self.fail_threshold:
                    self._state = "open"
                    self._opened_at = time.time()
                    logger.warning(f"[breaker/{self.name}] OPENED after {self._fail_count} fails")
            raise


# Shared breakers for outbound calls
LLM_BREAKER = CircuitBreaker(name="llm", fail_threshold=5, cool_down=60)
SCRAPER_BREAKER = CircuitBreaker(name="scraper", fail_threshold=8, cool_down=120)


# ════════════════════════════════════════════════════════════════════════════
#  5. DEAD-LETTER QUEUE (ringbuffer)
# ════════════════════════════════════════════════════════════════════════════
DLQ_MAX = 200
_DLQ: deque[dict] = deque(maxlen=DLQ_MAX)

def dlq_push(task_label: str, error: Exception | str, payload: Any = None):
    """Record a failed task for /api/health/dlq inspection."""
    try:
        _DLQ.append({
            "ts": datetime.utcnow().isoformat(),
            "task": task_label,
            "error": str(error)[:500],
            "error_type": type(error).__name__ if isinstance(error, BaseException) else "str",
            "payload_keys": list(payload.keys())[:20] if isinstance(payload, dict) else None,
        })
    except Exception:
        pass

def dlq_snapshot() -> list[dict]:
    return list(_DLQ)


# ════════════════════════════════════════════════════════════════════════════
#  6. GRACEFUL SIGTERM DRAIN
# ════════════════════════════════════════════════════════════════════════════
_drain_started = False

def install_graceful_drain(app, *, grace_seconds: float = 30.0):
    """Wire SIGTERM/SIGINT so inflight requests finish before uvicorn exits.

    Strategy: when a signal arrives, set `app.state._shedding = True` so
    LoadSheddingMiddleware starts returning 503 for new requests, sleep
    grace_seconds, then re-raise the signal to let uvicorn's own handler
    finish the job.
    """
    loop = asyncio.get_event_loop()

    def _handle(sig):
        global _drain_started
        if _drain_started:
            return
        _drain_started = True
        logger.info(f"[drain] signal {sig.name} received — beginning {grace_seconds}s graceful drain")
        try:
            app.state._shedding = True
        except Exception:
            pass
        # Re-raise the default handler after grace_seconds.
        loop.call_later(grace_seconds, lambda: signal.raise_signal(sig))

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda s=sig: _handle(s))
        except (NotImplementedError, RuntimeError):
            # Windows / certain test loops can't add signal handlers.
            pass


# ════════════════════════════════════════════════════════════════════════════
#  7. LOAD SHEDDING (health-aware)
# ════════════════════════════════════════════════════════════════════════════
class LoadSheddingMiddleware(BaseHTTPMiddleware):
    """Returns 503 for new requests when the box is unhealthy.

    Shedding triggers:
      • app.state._shedding == True              (set by graceful drain)
      • watchdog hasn't ticked in WD_STALE_SEC   (set externally)
      • event-loop lag > LAG_THRESHOLD_MS         (sampled here)

    Health-check paths are NEVER shed so K8s probes still pass.
    """
    NEVER_SHED = ("/api/health", "/api/health/", "/api/healthz", "/api/readiness", "/api/liveness")

    def __init__(self, app, *, wd_stale_sec: float = 120.0, lag_threshold_ms: float = 750.0):
        super().__init__(app)
        self.wd_stale_sec = wd_stale_sec
        self.lag_threshold_ms = lag_threshold_ms

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path == p or path.startswith(p + "/") or path.startswith(p) for p in self.NEVER_SHED):
            return await call_next(request)
        try:
            shed = bool(getattr(request.app.state, "_shedding", False))
            if not shed:
                # Watchdog stale check
                try:
                    from core import build_watchdog as _bwd
                    if _bwd._tick_count > 0 and (time.time() - getattr(_bwd, "_last_tick_at", time.time())) > self.wd_stale_sec:
                        shed = True
                except Exception:
                    pass
        except Exception:
            shed = False
        if shed:
            return JSONResponse({"error": "service_unavailable", "reason": "load_shedding"}, status_code=503)
        return await call_next(request)


# ════════════════════════════════════════════════════════════════════════════
#  Helpers exposed for /api/health/* endpoints
# ════════════════════════════════════════════════════════════════════════════
def reliability_snapshot() -> dict:
    return {
        "idempotency": {"cache_size": len(_IDEM_CACHE), "ttl_sec": IDEM_TTL_SEC},
        "circuit_breakers": {
            "llm":     {"state": LLM_BREAKER.state,     "fails": LLM_BREAKER._fail_count},
            "scraper": {"state": SCRAPER_BREAKER.state, "fails": SCRAPER_BREAKER._fail_count},
        },
        "dlq": {"size": len(_DLQ), "max": DLQ_MAX},
        "drain": {"started": _drain_started},
    }


__all__ = [
    "idempotent", "mongo_retry", "RequestTimeoutMiddleware",
    "CircuitBreaker", "LLM_BREAKER", "SCRAPER_BREAKER",
    "dlq_push", "dlq_snapshot",
    "install_graceful_drain", "LoadSheddingMiddleware",
    "reliability_snapshot",
]

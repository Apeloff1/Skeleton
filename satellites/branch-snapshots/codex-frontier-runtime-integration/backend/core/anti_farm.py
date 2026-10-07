"""
Lightweight in-process anti-farming primitives (single-worker uvicorn + GIL make
plain dict ops safe enough; held briefly). Two tools:
  • allow(key, rate_per_sec, burst): token-bucket throttle (returns False when empty)
  • claim_once(key, ttl): one-shot claim with TTL (returns False if already claimed)

Used to stop XP farming on /api/liveops/xp and ballot-stuffing on tournament votes.
State is per-process and resets on restart — acceptable for MVP abuse-resistance.
"""
from __future__ import annotations

import time
from typing import Dict, Tuple

_buckets: Dict[str, Tuple[float, float]] = {}   # key -> (tokens, last_refill)
_seen: Dict[str, float] = {}                     # key -> expiry epoch


def allow(key: str, rate_per_sec: float, burst: int) -> bool:
    now = time.time()
    tokens, last = _buckets.get(key, (float(burst), now))
    tokens = min(float(burst), tokens + (now - last) * rate_per_sec)
    if tokens < 1.0:
        _buckets[key] = (tokens, now)
        return False
    _buckets[key] = (tokens - 1.0, now)
    return True


def claim_once(key: str, ttl: float = 1800.0) -> bool:
    now = time.time()
    exp = _seen.get(key)
    if exp and exp > now:
        return False
    # opportunistic GC so the dict doesn't grow unbounded
    if len(_seen) > 50_000:
        for k in [k for k, v in list(_seen.items()) if v <= now]:
            _seen.pop(k, None)
    _seen[key] = now + ttl
    return True


def client_ip(request) -> str:
    """Best-effort client IP from proxy headers (X-Forwarded-For wins)."""
    fwd = (request.headers.get("x-forwarded-for", "") or "").split(",")[0].strip()
    if fwd:
        return fwd
    return request.client.host if getattr(request, "client", None) else "anon"


def rate_ok(request, action: str, rate_per_sec: float, burst: int) -> bool:
    """IP-scoped token-bucket guard for a named write action."""
    return allow(f"{action}:{client_ip(request)}", rate_per_sec, burst)

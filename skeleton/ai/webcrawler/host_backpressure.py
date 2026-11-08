"""Origin-wide retry backpressure under the canonical Dragon dispatch loop.

HTTP 429/503 is a host-level signal, not merely a per-URL retry. A server
quota or overload rejection must not let sibling frontier items evade the
cooldown. All decisions are finite, deterministic and capped; no network,
worker, database, or authority mutation is performed by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping
from email.utils import parsedate_to_datetime


_THROTTLE = frozenset({429, 503})
MAX_BACKOFF_SECONDS = 300.0


@dataclass(frozen=True)
class OriginThrottle:
    applies: bool
    status: int
    retry_seconds: float
    origin_ready_at: float | None
    header_accepted: bool
    affects_siblings: bool = True


def _header_seconds(raw: str | None, now: float) -> float | None:
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 128:
        return None
    value = raw.strip()
    # RFC 9110 Retry-After uses non-negative integer delay-seconds, not
    # floats, negative durations, JSON directives or header composites.
    if value.isascii() and value.isdecimal():
        if len(value) > 9:
            return MAX_BACKOFF_SECONDS
        return min(MAX_BACKOFF_SECONDS, float(int(value)))
    if value.lstrip("+-").replace(".", "", 1).isdigit():
        return None
    try:
        when = parsedate_to_datetime(value)
        if when.tzinfo is None:
            return None
        seconds = when.timestamp() - now
        if not math.isfinite(seconds):
            return None
        return min(MAX_BACKOFF_SECONDS, max(0.0, seconds))
    except (TypeError, ValueError, OverflowError):
        return None


def origin_throttle(
    status: int, headers: Mapping[str, str], *,
    now: float, attempts: int,
) -> OriginThrottle:
    if (
        type(status) is not int or not 100 <= status <= 599
        or not isinstance(headers, Mapping)
        or isinstance(now, bool) or not isinstance(now, (int, float))
        or not math.isfinite(now) or not 0 <= now <= 1e12
        or type(attempts) is not int or not 0 <= attempts <= 3
    ):
        raise ValueError("invalid canonical host throttle inputs")
    if status not in _THROTTLE:
        return OriginThrottle(False, status, 0.0, None, False, False)
    raw = next(
        (value for key, value in headers.items()
         if isinstance(key, str) and key.casefold() == "retry-after"),
        None,
    )
    user_seconds = _header_seconds(raw, now)
    fallback = min(MAX_BACKOFF_SECONDS, float(2 ** min(8, attempts + 1)))
    seconds = fallback if user_seconds is None else min(
        MAX_BACKOFF_SECONDS, max(fallback, user_seconds),
    )
    return OriginThrottle(
        applies=True, status=status,
        retry_seconds=seconds,
        origin_ready_at=now + seconds,
        header_accepted=user_seconds is not None,
    )

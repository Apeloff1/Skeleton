"""Retry policy: capped exponential backoff with deterministic full jitter.

Jitter is derived from (delivery_id, attempt) so schedules are reproducible
in tests and across process restarts, while still spreading thundering herds.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class RetryPolicy:
    base_seconds: float = 10.0
    factor: float = 2.0
    cap_seconds: float = 6 * 3600.0
    min_seconds: float = 1.0
    max_age_seconds: float | None = None  # dead-letter once a retry would land past this age

    def delay(self, delivery_id: str, attempt: int) -> float:
        """Delay before attempt ``attempt + 1`` (attempt is 1-based count so far)."""
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        ceiling = min(self.cap_seconds, self.base_seconds * self.factor ** (attempt - 1))
        h = hashlib.sha256(f"{delivery_id}:{attempt}".encode()).digest()
        frac = int.from_bytes(h[:8], "big") / 2 ** 64
        return round(max(self.min_seconds, ceiling / 2 + frac * ceiling / 2), 3)


LIMITS = {"base_seconds": (1.0, 3600.0), "factor": (1.0, 10.0), "cap_seconds": (1.0, 7 * 86400.0),
          "max_age_seconds": (60.0, 30 * 86400.0)}
POLICY_FIELDS = frozenset(LIMITS)


def policy_from_dict(data, default: "RetryPolicy | None" = None) -> RetryPolicy:
    """Validate a per-subscription policy body. Unset fields fall back to ``default``."""
    from .errors import validation
    if not isinstance(data, dict):
        raise validation("CORE.RETRY_POLICY.INVALID", "retry policy must be an object")
    unknown = set(data) - POLICY_FIELDS
    if unknown:
        raise validation("CORE.RETRY_POLICY.INVALID", "unknown fields", fields=sorted(unknown))
    base = default or RetryPolicy()
    values: dict = {}
    for name, (lo, hi) in LIMITS.items():
        if name not in data:
            continue
        v = data[name]
        if name == "max_age_seconds" and v is None:
            values[name] = None
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= float(v) <= hi:
            raise validation("CORE.RETRY_POLICY.INVALID", f"{name} must be a number in [{lo:g}, {hi:g}]",
                             field=name, min=lo, max=hi)
        values[name] = float(v)
    policy = RetryPolicy(base_seconds=values.get("base_seconds", base.base_seconds),
                         factor=values.get("factor", base.factor),
                         cap_seconds=values.get("cap_seconds", base.cap_seconds),
                         min_seconds=base.min_seconds,
                         max_age_seconds=values.get("max_age_seconds", base.max_age_seconds))
    if policy.cap_seconds < policy.base_seconds:
        raise validation("CORE.RETRY_POLICY.INVALID", "cap_seconds must be >= base_seconds",
                         field="cap_seconds")
    return policy


def policy_to_dict(p: RetryPolicy) -> dict:
    return {"base_seconds": p.base_seconds, "factor": p.factor, "cap_seconds": p.cap_seconds,
            "max_age_seconds": p.max_age_seconds}


def classify(status_code: int | None, error: str) -> str:
    """'success' | 'retry' | 'permanent'."""
    if status_code is not None and 200 <= status_code < 300:
        return "success"
    if status_code is None:
        return "permanent" if error.startswith("policy:") else "retry"
    if status_code in RETRYABLE_STATUS:
        return "retry"
    if status_code == 410:  # receiver says endpoint is gone
        return "permanent"
    return "retry" if status_code >= 500 else "permanent"

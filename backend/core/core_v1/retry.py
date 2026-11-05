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

    def delay(self, delivery_id: str, attempt: int) -> float:
        """Delay before attempt ``attempt + 1`` (attempt is 1-based count so far)."""
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        ceiling = min(self.cap_seconds, self.base_seconds * self.factor ** (attempt - 1))
        h = hashlib.sha256(f"{delivery_id}:{attempt}".encode()).digest()
        frac = int.from_bytes(h[:8], "big") / 2 ** 64
        return round(max(self.min_seconds, ceiling / 2 + frac * ceiling / 2), 3)


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

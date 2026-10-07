"""Pack F pipeline error taxonomy.

Every error raised by the composable request pipeline derives from
:class:`PipelineError` and carries a client-safe ``reason`` plus the HTTP
status the ASGI edge should map it to. ``retry_after_s`` (when set) is the
same field name and two-decimal rounding as ``RateLimitError`` in
``skeleton/api/middleware.py`` and Backend's Pack H pressure snapshot.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional


class PipelineError(Exception):
    """Base class for fail-closed pipeline outcomes."""

    status: int = 500
    reason: str = "pipeline_error"

    def __init__(self, detail: str = "", *, retry_after_s: Optional[float] = None) -> None:
        super().__init__(detail or self.reason)
        self.detail = detail or self.reason
        self.retry_after_s = None if retry_after_s is None else round(max(0.0, float(retry_after_s)), 2)

    def retry_after_header(self) -> Optional[str]:
        """``Retry-After`` value: whole seconds, rounded up, minimum 1."""
        if self.retry_after_s is None:
            return None
        return str(max(1, int(math.ceil(self.retry_after_s))))

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"error": self.reason, "status": self.status, "detail": self.detail}
        if self.retry_after_s is not None:
            out["retry_after_s"] = self.retry_after_s
        return out


class DeadlineExceeded(PipelineError):
    status = 504
    reason = "deadline_exceeded"


class AttemptTimeout(DeadlineExceeded):
    """A single attempt overran its per-attempt timeout (retryable)."""

    reason = "attempt_timeout"


class BreakerOpenError(PipelineError):
    status = 503
    reason = "circuit_open"

    def __init__(self, breaker: str, *, retry_after_s: Optional[float] = None) -> None:
        super().__init__(f"circuit {breaker!r} is open", retry_after_s=retry_after_s)
        self.breaker = breaker


class RetryBudgetExhausted(PipelineError):
    status = 503
    reason = "retry_budget_exhausted"


class PipelineConfigError(ValueError):
    """Invalid stage ordering or route configuration (raised at build time)."""


__all__ = [
    "AttemptTimeout",
    "BreakerOpenError",
    "DeadlineExceeded",
    "PipelineConfigError",
    "PipelineError",
    "RetryBudgetExhausted",
]

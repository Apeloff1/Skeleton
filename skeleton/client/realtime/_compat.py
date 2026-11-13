"""Import-guarded seams onto the SDK core (``skeleton.client``, PR #4095).

When ``skeleton.client.retry.RetryPolicy`` and
``skeleton.client.errors.SkeletonClientError`` exist they are used directly.
Until #4095 lands, same-named fallbacks with identical fields and signatures
are defined here so this package merges cleanly in either order. Nothing in
``skeleton/client/`` outside ``realtime/`` is created or edited.
"""

from __future__ import annotations

from dataclasses import dataclass

try:  # pragma: no cover - exercised once #4095 is on main
    from skeleton.client.retry import RetryPolicy  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - depends on merge order

    @dataclass(frozen=True)
    class RetryPolicy:  # type: ignore[no-redef]
        """Fallback mirror of ``skeleton.client.retry.RetryPolicy``."""

        max_attempts: int = 3
        base_delay_seconds: float = 0.1
        max_delay_seconds: float = 2.0
        retry_status_codes: frozenset = frozenset({408, 429, 500, 502, 503, 504})

        def __post_init__(self) -> None:
            if self.max_attempts < 1:
                raise ValueError("max_attempts must be >= 1")
            if self.base_delay_seconds <= 0 or self.max_delay_seconds <= 0:
                raise ValueError("delays must be positive")
            if self.base_delay_seconds > self.max_delay_seconds:
                raise ValueError("base_delay cannot exceed max_delay")

        def delay_for_attempt(self, attempt: int) -> float:
            """Delay before retrying after a failed attempt (0-based)."""
            if attempt < 0:
                raise ValueError("attempt must be >= 0")
            delay = self.base_delay_seconds * (2**attempt)
            return min(delay, self.max_delay_seconds)


try:  # pragma: no cover - exercised once #4095 is on main
    from skeleton.client.errors import SkeletonClientError  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - depends on merge order

    class SkeletonClientError(Exception):  # type: ignore[no-redef]
        """Fallback mirror of ``skeleton.client.errors.SkeletonClientError``."""


__all__ = ["RetryPolicy", "SkeletonClientError"]

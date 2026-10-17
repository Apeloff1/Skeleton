"""Cooperative cancellation for long-running client operations and streams."""

from __future__ import annotations

import threading

from skeleton.client.errors import SkeletonCancelledError


class CancelToken:
    """Thread-safe cancellation flag (``threading.Event`` based)."""

    __slots__ = ("_event", "_reason")

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason = "cancelled"

    def cancel(self, reason: str = "cancelled") -> None:
        self._reason = reason
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        return self._reason

    def wait(self, timeout: float | None = None) -> bool:
        """Block up to ``timeout`` seconds; return True if cancelled."""
        return self._event.wait(timeout)

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise SkeletonCancelledError(self._reason)

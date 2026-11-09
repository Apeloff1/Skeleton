"""Clocks, deadlines and cooperative cancellation.

All time-dependent components accept an injectable :class:`Clock` so tests
never sleep on the wall clock.  A :class:`Deadline` is an absolute point on a
monotonic clock; a :class:`CancellationToken` is a thread- and task-safe flag
with callbacks that adapters poll between I/O steps.
"""

from __future__ import annotations

import asyncio
import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol, TypeVar

from .errors import DeadlineExceededError, OperationCancelledError

__all__ = [
    "Clock",
    "MonotonicClock",
    "ManualClock",
    "Deadline",
    "CancellationToken",
    "run_with_deadline",
]

T = TypeVar("T")


class Clock(Protocol):
    def now(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...


class MonotonicClock:
    """Real monotonic clock backed by :func:`time.monotonic`."""

    def now(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        if seconds > 0:
            await asyncio.sleep(seconds)
        else:
            await asyncio.sleep(0)


class ManualClock:
    """Deterministic clock for tests: ``sleep`` advances time instantly."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = float(start)
        self.sleeps: list[float] = []
        self._lock = threading.Lock()

    def now(self) -> float:
        with self._lock:
            return self._now

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("cannot move a clock backwards")
        with self._lock:
            self._now += seconds

    async def sleep(self, seconds: float) -> None:
        seconds = max(0.0, float(seconds))
        self.sleeps.append(seconds)
        self.advance(seconds)
        await asyncio.sleep(0)


@dataclass(frozen=True)
class Deadline:
    """Absolute expiry on a clock.  ``expires_at`` of ``inf`` means none."""

    expires_at: float
    clock: Any = None

    @classmethod
    def after(cls, seconds: float | None, clock: Clock | None = None) -> "Deadline":
        clk = clock or MonotonicClock()
        if seconds is None:
            return cls(math.inf, clk)
        if seconds < 0:
            raise ValueError("deadline duration must be non-negative")
        return cls(clk.now() + float(seconds), clk)

    @classmethod
    def never(cls, clock: Clock | None = None) -> "Deadline":
        return cls(math.inf, clock or MonotonicClock())

    def _clock(self) -> Clock:
        return self.clock or MonotonicClock()

    @property
    def unbounded(self) -> bool:
        return math.isinf(self.expires_at)

    def remaining(self) -> float:
        if self.unbounded:
            return math.inf
        return max(0.0, self.expires_at - self._clock().now())

    def expired(self) -> bool:
        return not self.unbounded and self._clock().now() >= self.expires_at

    def check(self, what: str = "operation") -> None:
        if self.expired():
            raise DeadlineExceededError(f"{what} exceeded its deadline")

    def cap(self, timeout: float | None) -> float | None:
        """Return the tighter of ``timeout`` and the time remaining."""

        remaining = self.remaining()
        if timeout is None:
            return None if math.isinf(remaining) else remaining
        return min(float(timeout), remaining)

    def tighten(self, seconds: float | None) -> "Deadline":
        if seconds is None:
            return self
        other = self._clock().now() + float(seconds)
        return Deadline(min(self.expires_at, other), self.clock)


class CancellationToken:
    """Cooperative cancellation flag shared across threads and tasks."""

    def __init__(self, parent: "CancellationToken | None" = None) -> None:
        self._event = threading.Event()
        self._reason = ""
        self._callbacks: list[Callable[[str], None]] = []
        self._lock = threading.Lock()
        self._parent = parent
        if parent is not None:
            parent.on_cancel(self.cancel)

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        return self._reason

    def cancel(self, reason: str = "cancelled") -> None:
        with self._lock:
            if self._event.is_set():
                return
            self._reason = reason or "cancelled"
            self._event.set()
            callbacks = list(self._callbacks)
            self._callbacks.clear()
        for callback in callbacks:
            try:
                callback(self._reason)
            except Exception:  # noqa: BLE001 - one bad callback must not block others
                pass

    def on_cancel(self, callback: Callable[[str], None]) -> None:
        with self._lock:
            if not self._event.is_set():
                self._callbacks.append(callback)
                return
        callback(self._reason)

    def check(self) -> None:
        if self._event.is_set():
            raise OperationCancelledError(self._reason or "cancelled")

    def child(self) -> "CancellationToken":
        return CancellationToken(parent=self)

    async def wait(self, poll: float = 0.01) -> str:
        while not self._event.is_set():
            await asyncio.sleep(poll)
        return self._reason


async def run_with_deadline(
    factory: Callable[[], Awaitable[T]],
    *,
    timeout: float | None = None,
    deadline: Deadline | None = None,
    token: CancellationToken | None = None,
    what: str = "operation",
) -> T:
    """Await ``factory()`` bounded by a timeout, a deadline and a token.

    Raises :class:`DeadlineExceededError` on expiry and
    :class:`OperationCancelledError` when ``token`` fires first.  The inner
    task is always cancelled and awaited so no work leaks past the call.
    """

    if token is not None:
        token.check()
    effective = deadline.cap(timeout) if deadline is not None else timeout
    if deadline is not None:
        deadline.check(what)
    if effective is not None and effective <= 0:
        raise DeadlineExceededError(f"{what} exceeded its deadline")

    task = asyncio.ensure_future(factory())
    waiters: set[asyncio.Future[Any]] = {task}
    cancel_task: asyncio.Future[Any] | None = None
    if token is not None:
        cancel_task = asyncio.ensure_future(token.wait())
        waiters.add(cancel_task)
    try:
        done, _pending = await asyncio.wait(waiters, timeout=effective, return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            return task.result()
        if cancel_task is not None and cancel_task in done:
            raise OperationCancelledError(token.reason if token else "cancelled")
        raise DeadlineExceededError(f"{what} timed out after {effective:.3f}s")
    finally:
        for fut in waiters:
            if not fut.done():
                fut.cancel()
        for fut in waiters:
            if fut is not task or not fut.done() or fut.cancelled():
                try:
                    await fut
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

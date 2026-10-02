"""Deadlines and retry budgets for the Pack F request pipeline.

* :class:`Deadline` — an absolute monotonic expiry shared by every stage of
  one call. Child deadlines can only shrink, never extend, the parent.
* :class:`RetryBudget` — a Finagle-style token budget: every original
  request deposits ``retry_ratio`` of a token, every retry withdraws one,
  and a small ``min_retries_per_s`` floor keeps low-traffic routes able to
  retry at all. Bounding retries to a ratio of live traffic is what stops a
  brownout from turning into a retry storm.

Both read time through the injectable :class:`~skeleton.gate_plane.s2s.clock.Clock`.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Optional

from skeleton.gate_plane.s2s.clock import Clock, system_clock


@dataclass(frozen=True)
class Deadline:
    """Absolute monotonic deadline (``expires_at`` is ``clock.monotonic()`` seconds)."""

    expires_at: float
    clock: Clock

    @classmethod
    def after(cls, timeout_s: float, clock: Optional[Clock] = None) -> "Deadline":
        if timeout_s is None or timeout_s <= 0:
            raise ValueError("timeout_s must be > 0")
        clk = clock or system_clock()
        return cls(clk.monotonic() + float(timeout_s), clk)

    @classmethod
    def unbounded(cls, clock: Optional[Clock] = None) -> "Deadline":
        return cls(float("inf"), clock or system_clock())

    def remaining(self) -> float:
        return max(0.0, self.expires_at - self.clock.monotonic())

    def expired(self) -> bool:
        return self.clock.monotonic() >= self.expires_at

    @property
    def bounded(self) -> bool:
        return self.expires_at != float("inf")

    def child(self, timeout_s: Optional[float]) -> "Deadline":
        """A deadline that is the earlier of this one and ``now + timeout_s``."""
        if timeout_s is None or timeout_s <= 0:
            return self
        candidate = self.clock.monotonic() + float(timeout_s)
        return self if candidate >= self.expires_at else Deadline(candidate, self.clock)


class RetryBudget:
    """Sliding-window retry budget.

    ``balance = min_retries_per_s * window_s + deposits * retry_ratio - withdrawals``
    over the trailing ``window_s`` seconds. :meth:`try_withdraw` succeeds only
    while the balance is at least one whole token.
    """

    def __init__(
        self,
        *,
        retry_ratio: float = 0.2,
        min_retries_per_s: float = 1.0,
        window_s: float = 10.0,
        clock: Optional[Clock] = None,
        max_events: int = 100_000,
    ) -> None:
        if not 0.0 <= retry_ratio <= 10.0:
            raise ValueError("retry_ratio must be within [0, 10]")
        if min_retries_per_s < 0:
            raise ValueError("min_retries_per_s must be >= 0")
        if window_s <= 0:
            raise ValueError("window_s must be > 0")
        self.retry_ratio = float(retry_ratio)
        self.min_retries_per_s = float(min_retries_per_s)
        self.window_s = float(window_s)
        self._clock = clock or system_clock()
        self._deposits: Deque[float] = deque(maxlen=max_events)
        self._withdrawals: Deque[float] = deque(maxlen=max_events)
        self._denied = 0
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        horizon = now - self.window_s
        while self._deposits and self._deposits[0] <= horizon:
            self._deposits.popleft()
        while self._withdrawals and self._withdrawals[0] <= horizon:
            self._withdrawals.popleft()

    def _balance_unlocked(self) -> float:
        return (
            self.min_retries_per_s * self.window_s
            + len(self._deposits) * self.retry_ratio
            - len(self._withdrawals)
        )

    def deposit(self) -> None:
        """Record one original (non-retry) request."""
        with self._lock:
            now = self._clock.monotonic()
            self._prune(now)
            self._deposits.append(now)

    def try_withdraw(self) -> bool:
        """Spend one retry token; ``False`` (and nothing spent) when exhausted."""
        with self._lock:
            now = self._clock.monotonic()
            self._prune(now)
            if self._balance_unlocked() < 1.0:
                self._denied += 1
                return False
            self._withdrawals.append(now)
            return True

    def balance(self) -> float:
        with self._lock:
            self._prune(self._clock.monotonic())
            return self._balance_unlocked()

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            self._prune(self._clock.monotonic())
            return {
                "retry_ratio": self.retry_ratio,
                "min_retries_per_s": self.min_retries_per_s,
                "window_s": self.window_s,
                "deposits": len(self._deposits),
                "withdrawals": len(self._withdrawals),
                "denied": self._denied,
                "balance": round(self._balance_unlocked(), 3),
            }


class RetryBudgetRegistry:
    """Named budgets, typically one per upstream service."""

    def __init__(self, *, clock: Optional[Clock] = None, **defaults: Any) -> None:
        self._clock = clock or system_clock()
        self._defaults = defaults
        self._budgets: Dict[str, RetryBudget] = {}
        self._lock = threading.Lock()

    def get(self, name: str, **overrides: Any) -> RetryBudget:
        with self._lock:
            budget = self._budgets.get(name)
            if budget is None:
                kwargs = {**self._defaults, **overrides}
                budget = RetryBudget(clock=self._clock, **kwargs)
                self._budgets[name] = budget
            return budget

    def names(self) -> list:
        with self._lock:
            return sorted(self._budgets)

    def stats(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            items = list(self._budgets.items())
        return {name: b.stats() for name, b in sorted(items)}


__all__ = ["Deadline", "RetryBudget", "RetryBudgetRegistry"]

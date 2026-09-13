"""Deterministic sliding-window rate limiter."""
from collections import deque


class RateWindow:
    def __init__(self, limit: int, window: int = 60):
        if limit <= 0 or window <= 0:
            raise ValueError("invalid rate window")
        self.limit = limit
        self.window = window
        self._times = deque()
        self._last_now = None

    def _validate_now(self, now: int) -> None:
        if not isinstance(now, int):
            raise TypeError("now must be an integer")
        if self._last_now is not None and now < self._last_now:
            raise ValueError("rate window time must be monotonic")
        self._last_now = now

    def _trim(self, now: int):
        self._validate_now(now)
        while self._times and self._times[0] <= now - self.window:
            self._times.popleft()

    def allow(self, now: int) -> bool:
        self._trim(now)
        if len(self._times) >= self.limit:
            return False
        self._times.append(now)
        return True

    def remaining(self, now: int) -> int:
        self._trim(now)
        return max(0, self.limit - len(self._times))

    def retry_after(self, now: int) -> int:
        self._trim(now)
        return 0 if len(self._times) < self.limit else max(0, self._times[0] + self.window - now)

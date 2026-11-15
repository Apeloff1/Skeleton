"""Deterministic monotonic clock for bounded runtime components."""


class MonotonicClock:
    def __init__(self, start=0):
        if not isinstance(start, int):
            raise TypeError("start must be an integer")
        self._now = start

    @property
    def now(self):
        return self._now

    def advance(self, amount=1):
        if not isinstance(amount, int):
            raise TypeError("amount must be an integer")
        if amount < 0:
            raise ValueError("amount must be non-negative")
        self._now += amount
        return self._now

    def set(self, value):
        if not isinstance(value, int):
            raise TypeError("value must be an integer")
        if value < self._now:
            raise ValueError("clock cannot move backwards")
        self._now = value
        return self._now

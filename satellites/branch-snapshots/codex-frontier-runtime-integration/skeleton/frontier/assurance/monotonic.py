"""Monotonic sequence primitive for receipts, events, and replay."""


class MonotonicCounter:
    def __init__(self, start: int = 0):
        if start < 0:
            raise ValueError("start must be non-negative")
        self._value = start

    @property
    def value(self) -> int:
        return self._value

    def next(self) -> int:
        self._value += 1
        return self._value

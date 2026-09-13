"""Monotonic bounded sequence primitive for deterministic event ordering."""
class Sequence:
    def __init__(self, start: int = 0):
        if start < 0:
            raise ValueError("start must be non-negative")
        self._value = start

    @property
    def value(self):
        return self._value

    def next(self):
        if self._value >= 2**63 - 1:
            raise OverflowError("sequence exhausted")
        self._value += 1
        return self._value

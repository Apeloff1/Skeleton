"""Monotonic bounded sequence primitive for deterministic event ordering."""

MAX_SEQUENCE = 2**63 - 1


class Sequence:
    def __init__(self, start: int = 0):
        if not isinstance(start, int) or isinstance(start, bool) or start < 0 or start > MAX_SEQUENCE:
            raise ValueError("start must be an integer in the supported sequence range")
        self._value = start

    @property
    def value(self):
        return self._value

    def next(self):
        if self._value >= MAX_SEQUENCE:
            raise OverflowError("sequence exhausted")
        self._value += 1
        return self._value

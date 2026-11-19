"""Thread-safe in-process monotonic sequence primitive."""
from threading import Lock


class MonotonicCounter:
    def __init__(self, start: int = 0):
        if type(start) is not int or start < 0:
            raise ValueError("start must be a non-negative integer")
        self._value = start
        self._lock = Lock()

    @property
    def value(self) -> int:
        with self._lock:
            return self._value

    def next(self) -> int:
        with self._lock:
            self._value += 1
            return self._value

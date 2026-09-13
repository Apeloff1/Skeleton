"""Monotonic high-water mark contract."""

from threading import Lock


class Watermark:
    def __init__(self, value: int = -1):
        if not isinstance(value, int) or isinstance(value, bool) or value < -1:
            raise ValueError("value must be an integer >= -1")
        self._value = value
        self._lock = Lock()

    def observe(self, value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("value must be a non-negative integer")
        with self._lock:
            if value > self._value:
                self._value = value

    @property
    def value(self) -> int:
        with self._lock:
            return self._value

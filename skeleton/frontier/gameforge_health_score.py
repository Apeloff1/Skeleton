"""Bounded synchronized health observations; explicit readiness is available."""
from collections import deque
from threading import RLock


class HealthScore:
    def __init__(self, window=16, *, minimum_samples=0):
        if type(window) is not int or not 1 <= window <= 65_536:
            raise ValueError("bounded positive window required")
        if type(minimum_samples) is not int or not 0 <= minimum_samples <= window:
            raise ValueError("invalid minimum sample count")
        self._window = window
        self._minimum_samples = minimum_samples
        self._samples = deque(maxlen=window)
        self._lock = RLock()

    @property
    def window(self):
        return self._window

    def record(self, ok):
        if type(ok) is not bool:
            raise TypeError("ok must be bool")
        with self._lock:
            self._samples.append(ok)
            return self.value

    @property
    def value(self):
        with self._lock:
            return 1.0 if not self._samples else sum(self._samples) / len(self._samples)

    @property
    def healthy(self):
        with self._lock:
            return len(self._samples) >= self._minimum_samples and self.value >= 0.5

    @property
    def sample_count(self):
        with self._lock:
            return len(self._samples)

    @property
    def degraded(self):
        return not self.healthy

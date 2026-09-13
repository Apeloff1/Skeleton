"""Bounded health score derived from success/failure samples."""


class HealthScore:
    def __init__(self, window=16):
        if not isinstance(window, int) or window <= 0:
            raise ValueError("window must be positive")
        self.window = window
        self._samples = []

    def record(self, ok):
        self._samples.append(bool(ok))
        self._samples = self._samples[-self.window:]
        return self.value

    @property
    def value(self):
        return 1.0 if not self._samples else sum(self._samples) / len(self._samples)

    @property
    def healthy(self):
        return self.value >= 0.5

    @property
    def sample_count(self):
        return len(self._samples)

    @property
    def degraded(self):
        return not self.healthy

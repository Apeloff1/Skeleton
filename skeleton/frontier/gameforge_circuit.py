"""Circuit breaker with explicit recovery semantics."""
from enum import Enum
from threading import Lock


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class Circuit:
    def __init__(self, threshold: int = 5):
        if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold <= 0:
            raise ValueError("threshold must be a positive integer")
        self.threshold = threshold
        self.failures = 0
        self.state = CircuitState.CLOSED
        self._probe_in_flight = False
        self._lock = Lock()

    @property
    def allowed(self):
        with self._lock:
            return self.state is CircuitState.CLOSED

    @property
    def open(self):
        with self._lock:
            return self.state is CircuitState.OPEN

    def failure(self):
        with self._lock:
            self.failures += 1
            self._probe_in_flight = False
            if self.state is CircuitState.HALF_OPEN or self.failures >= self.threshold:
                self.state = CircuitState.OPEN
            return self.state

    def probe(self):
        with self._lock:
            if self.state is not CircuitState.OPEN or self._probe_in_flight:
                return False
            self.state = CircuitState.HALF_OPEN
            self._probe_in_flight = True
            return True

    def success(self):
        with self._lock:
            self.failures = 0
            self.state = CircuitState.CLOSED
            self._probe_in_flight = False

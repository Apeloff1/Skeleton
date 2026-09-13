"""Circuit breaker with explicit recovery semantics."""
from enum import Enum


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

    @property
    def allowed(self):
        return self.state is CircuitState.CLOSED or (
            self.state is CircuitState.HALF_OPEN and self._probe_in_flight
        )

    @property
    def open(self):
        return self.state is CircuitState.OPEN

    def failure(self):
        self.failures += 1
        self._probe_in_flight = False
        if self.state is CircuitState.HALF_OPEN or self.failures >= self.threshold:
            self.state = CircuitState.OPEN
        return self.state

    def probe(self):
        if self.state is CircuitState.OPEN:
            self.state = CircuitState.HALF_OPEN
            self._probe_in_flight = True
            return True
        return False

    def success(self):
        self.failures = 0
        self.state = CircuitState.CLOSED
        self._probe_in_flight = False

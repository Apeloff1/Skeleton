"""Monotonic checkpoint contract for replay-safe consumers."""

from threading import Lock


class Checkpoint:
    def __init__(self, sequence: int = -1):
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < -1:
            raise ValueError("sequence must be an integer >= -1")
        self._sequence = sequence
        self._lock = Lock()

    def advance(self, sequence: int) -> bool:
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        with self._lock:
            if sequence <= self._sequence:
                return False
            self._sequence = sequence
            return True

    @property
    def sequence(self):
        with self._lock:
            return self._sequence

"""Process-local atomic one-shot fence; persistence is an external concern."""
from threading import Lock


class ExecutionFenceV2:
    def __init__(self):
        self._closed = False
        self._lock = Lock()

    @property
    def closed(self):
        with self._lock:
            return self._closed

    def acquire(self):
        with self._lock:
            if self._closed:
                return False
            self._closed = True
            return True

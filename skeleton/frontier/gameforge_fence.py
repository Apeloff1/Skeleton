"""Synchronized process-local operation fence; use closed startup for new owners."""
from threading import Lock


class Fence:
    def __init__(self, open_: bool = True):
        if type(open_) is not bool:
            raise ValueError("explicit boolean fence state required")
        self._open = open_
        self._lock = Lock()

    def close(self) -> None:
        with self._lock:
            self._open = False

    def open(self) -> None:
        with self._lock:
            self._open = True

    def allow(self) -> bool:
        with self._lock:
            return self._open

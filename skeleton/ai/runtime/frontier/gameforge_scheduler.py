"""Bounded deterministic weighted scheduling without expanding the weight vector."""
from bisect import bisect_right
from collections.abc import Mapping
from threading import Lock

MAX_TARGETS = 4096
MAX_TOTAL_WEIGHT = 1 << 30


class Scheduler:
    def __init__(self, weights):
        if not isinstance(weights, Mapping) or not 1 <= len(weights) <= MAX_TARGETS:
            raise ValueError("bounded scheduler targets required")
        names = []
        ends = []
        total = 0
        for name, weight in weights.items():
            if type(name) is not str or not name.strip() or len(name) > 256:
                raise ValueError("invalid scheduler target")
            if type(weight) is not int or not 1 <= weight <= MAX_TOTAL_WEIGHT - total:
                raise ValueError("positive integer weights within aggregate limit required")
            names.append(name)
            total += weight
            ends.append(total)
        self._names = tuple(names)
        self._ends = tuple(ends)
        self._size = total
        self._cursor = 0
        self._lock = Lock()

    @property
    def size(self):
        return self._size

    @property
    def cursor(self):
        with self._lock:
            return self._cursor

    def next(self):
        with self._lock:
            name = self._names[bisect_right(self._ends, self._cursor)]
            self._cursor = (self._cursor + 1) % self._size
            return name

    def reset(self):
        with self._lock:
            self._cursor = 0

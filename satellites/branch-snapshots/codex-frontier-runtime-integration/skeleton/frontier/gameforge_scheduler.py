"""Bounded weighted work scheduler with deterministic weighted round-robin."""


class Scheduler:
    def __init__(self, weights):
        if not weights or any(not isinstance(v, int) or v <= 0 for v in weights.values()):
            raise ValueError("positive integer weights required")
        self._schedule = tuple(name for name, weight in weights.items() for _ in range(weight))
        self._cursor = 0
        self._weights = dict(weights)

    @property
    def size(self):
        return len(self._schedule)

    @property
    def cursor(self):
        return self._cursor

    def next(self):
        name = self._schedule[self._cursor]
        self._cursor = (self._cursor + 1) % len(self._schedule)
        return name

    def reset(self):
        self._cursor = 0

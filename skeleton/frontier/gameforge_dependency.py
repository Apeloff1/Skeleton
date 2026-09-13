"""Dependency gate: readiness is fail-closed until all required checks pass."""


class DependencyGate:
    def __init__(self, dependencies):
        required = set(dependencies)
        if any(not name for name in required):
            raise ValueError("dependency names must be non-empty")
        self._required = required
        self._ready = set()

    def mark(self, name, ready=True):
        if name not in self._required:
            raise KeyError(name)
        if not isinstance(ready, bool):
            raise TypeError("ready must be bool")
        if ready:
            self._ready.add(name)
        else:
            self._ready.discard(name)
        return self.ready

    @property
    def required(self):
        return frozenset(self._required)

    @property
    def pending(self):
        return frozenset(self._required - self._ready)

    @property
    def ready_count(self):
        return len(self._ready)

    @property
    def ready(self):
        return self._required.issubset(self._ready)

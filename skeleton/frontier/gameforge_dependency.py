"""Dependency gate: readiness is fail-closed until all required checks pass."""


class DependencyGate:
    def __init__(self, dependencies):
        if isinstance(dependencies, (str, bytes)):
            raise TypeError("dependencies must be an iterable of names")
        required = set(dependencies)
        if not required or any(not isinstance(name, str) or not name.strip() for name in required):
            raise ValueError("at least one non-empty dependency name is required")
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

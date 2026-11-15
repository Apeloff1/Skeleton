"""Synchronized dependency readiness with optional bounded evidence lifetime."""
from threading import RLock
from time import monotonic
from math import isfinite


class DependencyGate:
    def __init__(self, dependencies, *, ttl_seconds=None, clock=monotonic):
        if isinstance(dependencies, (str, bytes)):
            raise TypeError("dependencies must be an iterable of names")
        required = set()
        for index, name in enumerate(dependencies):
            if index >= 4096 or type(name) is not str or not name.strip() or len(name) > 256:
                raise ValueError("bounded dependency inventory required")
            required.add(name)
        if not required:
            raise ValueError("at least one dependency is required")
        if ttl_seconds is not None and (type(ttl_seconds) not in (int, float)
                or not isfinite(ttl_seconds) or not 0 < ttl_seconds <= 86400):
            raise ValueError("invalid dependency evidence lifetime")
        if not callable(clock):
            raise ValueError("clock required")
        self._required = frozenset(required)
        self._ready = {}
        self._ttl = ttl_seconds
        self._clock = clock
        self._lock = RLock()

    def _live(self):
        if self._ttl is None:
            return set(self._ready)
        now = self._clock()
        if type(now) not in (int, float) or not isfinite(now):
            return set()
        return {name for name, stamp in self._ready.items() if 0 <= now - stamp < self._ttl}

    def mark(self, name, ready=True):
        if name not in self._required:
            raise KeyError(name)
        if type(ready) is not bool:
            raise TypeError("ready must be bool")
        with self._lock:
            if ready:
                stamp = self._clock() if self._ttl is not None else 0
                if type(stamp) not in (int, float) or not isfinite(stamp):
                    self._ready.pop(name, None)
                    raise ValueError("invalid readiness clock")
                self._ready[name] = stamp
            else:
                self._ready.pop(name, None)
            return self.ready

    @property
    def required(self):
        return self._required

    @property
    def pending(self):
        with self._lock:
            return frozenset(self._required - self._live())

    @property
    def ready_count(self):
        with self._lock:
            return len(self._live())

    @property
    def ready(self):
        return not self.pending

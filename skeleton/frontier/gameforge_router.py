"""Synchronized round-robin routing with optional explicit fresh health evidence."""
from threading import RLock
from math import isfinite
from time import monotonic


class HealthRouter:
    def __init__(self, targets, *, require_probe=False, ttl_seconds=None, clock=monotonic):
        if isinstance(targets, (str, bytes)) or type(require_probe) is not bool:
            raise ValueError("target inventory and explicit probe policy required")
        names = []
        for index, target in enumerate(targets):
            if index >= 4096 or type(target) is not str or not target.strip() or len(target) > 1024:
                raise ValueError("invalid bounded target inventory")
            names.append(target)
        self._targets = tuple(dict.fromkeys(names))
        if not self._targets:
            raise ValueError("targets required")
        if ttl_seconds is not None and (type(ttl_seconds) not in (int, float)
                or not isfinite(ttl_seconds) or not 0 < ttl_seconds <= 86400):
            raise ValueError("invalid health evidence lifetime")
        self._ttl = ttl_seconds
        self._clock = clock
        self._healthy = {} if require_probe or ttl_seconds is not None else dict.fromkeys(self._targets, 0)
        self._cursor = -1
        self._lock = RLock()

    def _live(self):
        if self._ttl is None:
            return set(self._healthy)
        now = self._clock()
        if type(now) not in (int, float) or not isfinite(now):
            return set()
        return {name for name, stamp in self._healthy.items() if 0 <= now - stamp < self._ttl}

    def mark(self, target, healthy):
        if target not in self._targets:
            raise KeyError(target)
        if type(healthy) is not bool:
            raise ValueError("explicit boolean health required")
        with self._lock:
            if healthy:
                stamp = self._clock() if self._ttl is not None else 0
                if type(stamp) not in (int, float) or not isfinite(stamp):
                    self._healthy.pop(target, None)
                    raise ValueError("invalid health clock")
                self._healthy[target] = stamp
            else:
                self._healthy.pop(target, None)

    def next(self):
        with self._lock:
            live = self._live()
            for _ in self._targets:
                self._cursor = (self._cursor + 1) % len(self._targets)
                target = self._targets[self._cursor]
                if target in live:
                    return target
            return None

    @property
    def healthy(self):
        with self._lock:
            live = self._live()
            return tuple(x for x in self._targets if x in live)

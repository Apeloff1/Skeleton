"""Chaos governor — the degradation ladder, with a bounded window.

Rungs: NORMAL -> REDUCED_CACHING -> SHED_BACKGROUND -> STALE_READS ->
EMERGENCY_READ_ONLY. The governor grades components on observed truth —
its rolling error window — never on self-report. The window itself is
capped (reservoir sampling past 10k observations): the governor must
survive the flood it governs.
"""

from __future__ import annotations

import random
import threading
import time
from enum import IntEnum


class Rung(IntEnum):
    NORMAL = 0
    REDUCED_CACHING = 1
    SHED_BACKGROUND = 2
    STALE_READS = 3
    EMERGENCY_READ_ONLY = 4


_WINDOW_SPAN_SECS = 30.0
_HARD_CAP = 10_000
_MIN_SAMPLE = 16
_ESCALATE_AT = 0.25
_RECOVER_AT = 0.05


class Governor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rung = Rung.NORMAL
        self._window: list[tuple[float, bool]] = []
        self._seen = 0

    @property
    def rung(self) -> Rung:
        return self._rung

    def observe(self, ok: bool) -> None:
        now = time.monotonic()
        with self._lock:
            self._seen += 1
            if len(self._window) < _HARD_CAP:
                self._window.append((now, ok))
            else:
                # Reservoir: past the cap, each observation replaces a slot
                # with probability cap/seen — statistically sound, bounded.
                j = random.randrange(self._seen)
                if j < _HARD_CAP:
                    self._window[j] = (now, ok)
            cutoff = now - _WINDOW_SPAN_SECS
            self._window = [(t, o) for (t, o) in self._window if t > cutoff]
            n = len(self._window)
            if n < _MIN_SAMPLE:
                return
            rate = sum(1 for _, o in self._window if not o) / n
            if rate > _ESCALATE_AT and self._rung < Rung.EMERGENCY_READ_ONLY:
                self._rung = Rung(self._rung + 1)
            elif rate < _RECOVER_AT and self._rung > Rung.NORMAL:
                self._rung = Rung(self._rung - 1)

    def permits_writes(self) -> bool:
        return self._rung < Rung.EMERGENCY_READ_ONLY

    def permits_background(self) -> bool:
        return self._rung < Rung.SHED_BACKGROUND

    def should_cache(self) -> bool:
        return self._rung < Rung.REDUCED_CACHING

    def stats(self) -> dict:
        with self._lock:
            return {
                "rung": self._rung.name.lower(),
                "window": len(self._window),
                "permits_writes": self.permits_writes(),
                "permits_background": self.permits_background(),
            }

"""chaos — progressive degradation ladder (gameforge-rs chaos::Governor port).

Watches a rolling error window and climbs/descends rungs. Byzantine in
spirit: grades components on observed truth, never on self-report.

Named ``ChaosGovernor`` to avoid clashing with ``skeleton.kernel.governor``
(mid-run profile pressure tick). Existing ``governor.py`` is left untouched.
"""

from __future__ import annotations

import threading
import time
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple


class Rung(IntEnum):
    """Progressive degradation ladder. Names match gameforge-rs."""

    NORMAL = 0
    REDUCED_CACHING = 1
    SHED_BACKGROUND = 2
    STALE_READS = 3
    EMERGENCY_READ_ONLY = 4

    def name(self) -> str:  # type: ignore[override]
        return {
            Rung.NORMAL: "normal",
            Rung.REDUCED_CACHING: "reduced_caching",
            Rung.SHED_BACKGROUND: "shed_background",
            Rung.STALE_READS: "stale_reads",
            Rung.EMERGENCY_READ_ONLY: "emergency_read_only",
        }[self]


class ChaosGovernor:
    """Rolling-window error governor. Sync port of gf ``chaos::Governor``."""

    def __init__(
        self,
        *,
        window_span: float = 30.0,
        escalate_at: float = 0.25,
        recover_at: float = 0.05,
        min_samples: int = 16,
    ) -> None:
        self._rung = Rung.NORMAL
        self._window: List[Tuple[float, bool]] = []
        self._window_span = float(window_span)
        self._escalate_at = float(escalate_at)
        self._recover_at = float(recover_at)
        self._min_samples = int(min_samples)
        self._lock = threading.Lock()

    def rung(self) -> Rung:
        with self._lock:
            return self._rung

    def observe(self, ok: bool) -> None:
        with self._lock:
            now = time.monotonic()
            self._window.append((now, bool(ok)))
            cutoff = now - self._window_span
            self._window = [(t, o) for (t, o) in self._window if t > cutoff]
            if len(self._window) < self._min_samples:
                return
            errs = sum(1 for (_, o) in self._window if not o)
            rate = errs / len(self._window)
            cur = int(self._rung)
            if rate > self._escalate_at and cur < int(Rung.EMERGENCY_READ_ONLY):
                self._rung = Rung(cur + 1)
            elif rate < self._recover_at and cur > 0:
                self._rung = Rung(cur - 1)

    def permits_writes(self) -> bool:
        return self.rung() < Rung.EMERGENCY_READ_ONLY

    def permits_background(self) -> bool:
        return self.rung() < Rung.SHED_BACKGROUND

    def should_cache(self) -> bool:
        return self.rung() < Rung.REDUCED_CACHING

    def stats(self) -> Dict[str, Any]:
        r = self.rung()
        return {
            "rung": r.name(),
            "permits_writes": self.permits_writes(),
            "permits_background": self.permits_background(),
        }

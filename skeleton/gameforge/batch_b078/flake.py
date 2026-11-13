"""B078 — Flake detection and quarantine with expiry.

Success criterion: "Flaky tests are detected statistically, isolated
temporarily and forced back to ownership."

* Detection: a test is flaky when, for the *same* B072 evidence key (seed +
  code revision), it has both passed and failed, and the failure rate's Wilson
  lower bound exceeds ``min_rate`` with at least ``min_runs`` observations.
  Different outcomes under different seeds are real bugs, not flakes.
* Quarantine: requires a named owner and an expiry date (max ``max_days``).
* Expiry: :meth:`FlakeTracker.enforce` returns expired entries, which
  callers must treat as hard failures assigned to the owner.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Tuple


class FlakeError(ValueError):
    pass


@dataclass(frozen=True)
class RunRecord:
    test_id: str
    revision: str
    seed: int
    passed: bool


@dataclass(frozen=True)
class QuarantineEntry:
    test_id: str
    owner: str
    reason: str
    since: date
    expires: date


def wilson_lower(failures: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = failures / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denom)


class FlakeTracker:
    def __init__(self, min_runs: int = 10, min_rate: float = 0.02, max_days: int = 14) -> None:
        self.min_runs, self.min_rate, self.max_days = min_runs, min_rate, max_days
        self._runs: Dict[Tuple[str, str, int], List[bool]] = {}
        self.quarantine: Dict[str, QuarantineEntry] = {}

    def record(self, r: RunRecord) -> None:
        self._runs.setdefault((r.test_id, r.revision, r.seed), []).append(r.passed)

    def flaky(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for (tid, _rev, _seed), outcomes in self._runs.items():
            n, f = len(outcomes), outcomes.count(False)
            if n < self.min_runs or f == 0 or f == n:
                continue
            lb = wilson_lower(f, n)
            if lb >= self.min_rate:
                out[tid] = max(out.get(tid, 0.0), lb)
        return out

    def quarantine_test(self, test_id: str, owner: str, reason: str, today: date, days: int) -> QuarantineEntry:
        if test_id not in self.flaky():
            raise FlakeError(f"{test_id} is not statistically flaky; fix it instead")
        if not owner.strip():
            raise FlakeError("quarantine requires an owner")
        if not 0 < days <= self.max_days:
            raise FlakeError(f"quarantine must be 1..{self.max_days} days")
        e = QuarantineEntry(test_id, owner, reason, today, today + timedelta(days=days))
        self.quarantine[test_id] = e
        return e

    def is_quarantined(self, test_id: str, today: date) -> bool:
        e = self.quarantine.get(test_id)
        return e is not None and today < e.expires

    def enforce(self, today: date) -> List[QuarantineEntry]:
        """Remove and return expired entries; callers must fail these back to their owners."""
        expired = [e for e in self.quarantine.values() if today >= e.expires]
        for e in expired:
            del self.quarantine[e.test_id]
        return sorted(expired, key=lambda e: e.test_id)

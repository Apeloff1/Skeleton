"""Confidence calibration — make stated confidence mean what it says.

Wave-3 SOTA (agentic confidence calibration line): a system that says
"90% confident" should be right ~90% of the time — and when it isn't,
the stated number should be corrected before anyone acts on it. This
ledger records (stated, correct) outcomes, computes expected calibration
error (ECE) per band, and maps raw confidence through the measured
correction curve.

Pure domain. Consumers: Jeeves traces, swarm consensus ballots,
verification verdicts — anything that emits a confidence number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class CalibrationRecord:
    stated: float
    correct: bool
    channel: str = "default"


class CalibrationLedger:
    """Outcome ledger + isotonic-lite correction for stated confidence."""

    BANDS = 10

    def __init__(self, *, min_samples: int = 20) -> None:
        self.min_samples = min_samples
        self._records: List[CalibrationRecord] = []

    def record(self, stated: float, correct: bool, *, channel: str = "default") -> None:
        stated = min(1.0, max(0.0, float(stated)))
        self._records.append(CalibrationRecord(stated, bool(correct), channel))

    # ------------------------------------------------------------------
    # Measurement
    # ------------------------------------------------------------------

    def _band_stats(self, channel: Optional[str] = None) -> List[Tuple[float, float, int]]:
        """Per-band (mean stated, empirical accuracy, count)."""
        recs = [r for r in self._records if channel is None or r.channel == channel]
        buckets: List[List[CalibrationRecord]] = [[] for _ in range(self.BANDS)]
        for r in recs:
            buckets[min(self.BANDS - 1, int(r.stated * self.BANDS))].append(r)
        out = []
        for bucket in buckets:
            if bucket:
                mean_stated = sum(r.stated for r in bucket) / len(bucket)
                acc = sum(1 for r in bucket if r.correct) / len(bucket)
                out.append((mean_stated, acc, len(bucket)))
        return out

    def expected_calibration_error(self, channel: Optional[str] = None) -> float:
        stats = self._band_stats(channel)
        total = sum(n for _, _, n in stats)
        if total == 0:
            return 0.0
        return sum(abs(stated - acc) * n for stated, acc, n in stats) / total

    # ------------------------------------------------------------------
    # Correction
    # ------------------------------------------------------------------

    def correct(self, stated: float, *, channel: Optional[str] = None) -> float:
        """Map a stated confidence through measured accuracy for its band.

        Below ``min_samples`` the mapping is identity — never correct on
        vibes. Above it, the band's empirical accuracy replaces the claim.
        """
        stated = min(1.0, max(0.0, float(stated)))
        recs = [r for r in self._records if channel is None or r.channel == channel]
        if len(recs) < self.min_samples:
            return stated
        band = min(self.BANDS - 1, int(stated * self.BANDS))
        bucket = [r for r in recs if min(self.BANDS - 1, int(r.stated * self.BANDS)) == band]
        if not bucket:
            return stated
        return round(sum(1 for r in bucket if r.correct) / len(bucket), 4)

    def stats(self) -> Dict[str, Any]:
        return {
            "records": len(self._records),
            "ece": round(self.expected_calibration_error(), 4),
            "channels": sorted({r.channel for r in self._records}),
            "ready": len(self._records) >= self.min_samples,
        }

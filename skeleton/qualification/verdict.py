from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"  # evidence missing / not attributable to the head under test

    @property
    def rank(self) -> int:
        return {"pass": 0, "blocked": 1, "fail": 2}[self.value]


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    gate: str
    verdict: Verdict
    reasons: tuple[str, ...] = ()
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "gate": self.gate,
            "verdict": self.verdict.value,
            "reasons": list(self.reasons),
            "metrics": dict(self.metrics),
        }


def aggregate(results: Iterable[CaseResult]) -> Verdict:
    """Worst verdict wins; an empty run is BLOCKED, never PASS."""
    worst = None
    for r in results:
        if worst is None or r.verdict.rank > worst.rank:
            worst = r.verdict
    return worst or Verdict.BLOCKED

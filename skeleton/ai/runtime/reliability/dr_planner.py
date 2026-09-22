"""DR planner — disaster recovery objectives, runbooks, and drills.

Defines RPO/RTO targets per subsystem, maps recovery runbooks to
failure scenarios, and tracks drill execution. Drills simulate a
failure, run the recovery runbook, and verify RTO/RPO were met.
Results feed the resilience score.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class DRObjective:
    subsystem: str
    rpo_s: float
    rto_s: float
    tier: str = "standard"


@dataclass
class Runbook:
    name: str
    scenario: str
    steps: List[Callable[[], bool]]
    subsystem: str


@dataclass
class DrillResult:
    runbook: str
    started_ns: int
    duration_s: float
    steps_passed: int
    steps_total: int
    rto_met: bool
    rpo_met: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "runbook": self.runbook,
            "duration_s": round(self.duration_s, 2),
            "steps_passed": self.steps_passed,
            "steps_total": self.steps_total,
            "rto_met": self.rto_met,
            "rpo_met": self.rpo_met,
            "passed": self.steps_passed == self.steps_total and self.rto_met,
        }


class DRPlanner:
    """Disaster recovery objectives, runbooks, and drill execution."""

    def __init__(self):
        self._objectives: Dict[str, DRObjective] = {}
        self._runbooks: Dict[str, Runbook] = {}
        self._drills: List[DrillResult] = []

    def set_objective(self, subsystem: str, rpo_s: float, rto_s: float,
                      tier: str = "standard") -> DRObjective:
        obj = DRObjective(subsystem=subsystem, rpo_s=rpo_s, rto_s=rto_s, tier=tier)
        self._objectives[subsystem] = obj
        return obj

    def add_runbook(self, name: str, scenario: str, subsystem: str,
                    steps: List[Callable[[], bool]]) -> Runbook:
        rb = Runbook(name=name, scenario=scenario, subsystem=subsystem, steps=steps)
        self._runbooks[name] = rb
        return rb

    def run_drill(self, runbook_name: str, last_backup_age_s: float = 0.0) -> DrillResult:
        rb = self._runbooks[runbook_name]
        obj = self._objectives.get(rb.subsystem)
        start = time.time_ns()
        passed = 0
        for step in rb.steps:
            try:
                if step():
                    passed += 1
            except Exception:  # noqa: BLE001
                pass
        duration_s = (time.time_ns() - start) / 1e9
        result = DrillResult(
            runbook=runbook_name,
            started_ns=start,
            duration_s=duration_s,
            steps_passed=passed,
            steps_total=len(rb.steps),
            rto_met=(duration_s <= obj.rto_s) if obj else True,
            rpo_met=(last_backup_age_s <= obj.rpo_s) if obj else True,
        )
        self._drills.append(result)
        return result

    def coverage(self) -> Dict[str, Any]:
        covered = {rb.subsystem for rb in self._runbooks.values()}
        gaps = [s for s in self._objectives if s not in covered]
        untested = [rb.subsystem for rb in self._runbooks.values()
                    if not any(d.runbook == rb.name for d in self._drills)]
        return {
            "subsystems_with_objectives": len(self._objectives),
            "runbooks": len(self._runbooks),
            "coverage_gaps": gaps,
            "untested_runbooks": sorted(set(untested)),
        }

    def drill_pass_rate(self) -> float:
        if not self._drills:
            return 1.0
        passed = sum(1 for d in self._drills if d.to_dict()["passed"])
        return passed / len(self._drills)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "dr-planner-card",
            "objectives": {s: {"rpo_s": o.rpo_s, "rto_s": o.rto_s, "tier": o.tier} for s, o in self._objectives.items()},
            "coverage": self.coverage(),
            "drills_run": len(self._drills),
            "drill_pass_rate": round(self.drill_pass_rate(), 3),
            "recent_drills": [d.to_dict() for d in self._drills[-5:]],
        }

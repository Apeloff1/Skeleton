"""B079 — Cross-platform compatibility matrix.

Success criterion: "Core scenarios run on supported targets and differences are
explicit evidence, not assumptions."

The matrix is (supported platform x core scenario). Every cell must hold an
observed :class:`ScenarioOutcome`: functional pass/fail, a B074 budget
:class:`GateResult`, and an optional B075 capture digest. A cell with no
observation is ``unknown`` and blocks — never assumed to pass. Visual
differences across platforms are only allowed when explicitly declared.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from skeleton.gameforge.batch_b074 import GateResult


class MatrixError(ValueError):
    pass


@dataclass(frozen=True)
class Platform:
    name: str
    budget_target: str


@dataclass(frozen=True)
class ScenarioOutcome:
    passed: bool
    budget: GateResult
    capture_digest: Optional[str] = None
    note: str = ""


class CompatMatrix:
    def __init__(self, platforms: List[Platform], scenarios: List[str]) -> None:
        if not platforms or not scenarios:
            raise MatrixError("matrix needs platforms and scenarios")
        self.platforms = {p.name: p for p in platforms}
        self.scenarios = list(scenarios)
        self.cells: Dict[Tuple[str, str], ScenarioOutcome] = {}
        self.declared_visual_diffs: Set[Tuple[str, str]] = set()

    def observe(self, platform: str, scenario: str, outcome: ScenarioOutcome) -> None:
        p = self.platforms.get(platform)
        if p is None or scenario not in self.scenarios:
            raise MatrixError(f"unknown cell {platform}/{scenario}")
        if outcome.budget.target != p.budget_target:
            raise MatrixError(f"budget evidence for {outcome.budget.target}, expected {p.budget_target}")
        self.cells[(platform, scenario)] = outcome

    def declare_visual_difference(self, platform: str, scenario: str) -> None:
        self.declared_visual_diffs.add((platform, scenario))

    def evaluate(self) -> Dict[str, List[str]]:
        problems: Dict[str, List[str]] = {"unknown": [], "failed": [], "over_budget": [], "visual_drift": []}
        for s in self.scenarios:
            digests: Dict[str, List[str]] = {}
            for pname in sorted(self.platforms):
                cell = f"{pname}/{s}"
                o = self.cells.get((pname, s))
                if o is None:
                    problems["unknown"].append(cell)
                    continue
                if not o.passed:
                    problems["failed"].append(cell)
                if not o.budget.passed:
                    problems["over_budget"].append(cell)
                if o.capture_digest and (pname, s) not in self.declared_visual_diffs:
                    digests.setdefault(o.capture_digest, []).append(pname)
            if len(digests) > 1:
                problems["visual_drift"].append(f"{s}: " + " vs ".join(
                    ",".join(v) for _, v in sorted(digests.items(), key=lambda kv: kv[1])))
        return problems

    @property
    def green(self) -> bool:
        return not any(self.evaluate().values())

    def to_dict(self) -> dict:
        return {"platforms": sorted(self.platforms), "scenarios": self.scenarios,
                "cells": {f"{p}/{s}": {"passed": o.passed, "budget_passed": o.budget.passed,
                                       "capture": o.capture_digest, "note": o.note}
                          for (p, s), o in sorted(self.cells.items())},
                "problems": self.evaluate()}

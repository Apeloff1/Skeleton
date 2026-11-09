"""Score a GamePlan and turn it into accept / repair / regenerate."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping

from skeleton.forge.validator import Severity

from .playability import check_cycles, check_reachability, check_winnable
from .references import check_references
from .schema import check_schema

ACCEPT, REPAIR, REGENERATE = "accept", "repair", "regenerate"
# Errors in these rules mean the plan is not a plan: regenerate, don't patch.
FATAL_RULES = frozenset({"schema"})
WEIGHTS = {"schema": 0.4, "references": 0.25, "reachability": 0.15, "winnable": 0.1, "logic_loop": 0.1}


@dataclass(frozen=True)
class Thresholds:
    accept: float = 0.85
    repair: float = 0.5
    error_penalty: float = 1.0   # fraction of a rule's weight lost per error (capped)
    warning_penalty: float = 0.2

    def __post_init__(self) -> None:
        vals = (self.repair, self.accept, self.error_penalty, self.warning_penalty)
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in vals):
            raise ValueError("scoring thresholds must be finite numbers")
        if not 0.0 <= self.repair <= self.accept <= 1.0:
            raise ValueError("need 0 <= repair <= accept <= 1")
        if not 0.0 <= self.error_penalty <= 1.0 or not 0.0 <= self.warning_penalty <= 1.0:
            raise ValueError("scoring penalties must be within [0,1]")


@dataclass(frozen=True)
class Verdict:
    verdict: str
    score: float
    problems: tuple = ()
    by_rule: Mapping[str, float] = field(default_factory=dict)

    @property
    def errors(self) -> list:
        return [p for p in self.problems if p.severity is Severity.ERROR]

    def as_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "score": round(self.score, 4), "by_rule": dict(self.by_rule),
                "problems": [{"rule": p.rule, "severity": p.severity.value, "message": p.message}
                             for p in self.problems]}


def validate_plan(plan: Any) -> list:
    problems = check_schema(plan)
    if not isinstance(plan, Mapping):
        return problems
    for check in (check_references, check_reachability, check_winnable, check_cycles):
        problems.extend(check(plan))
    if isinstance(plan.get("procgen"), Mapping):
        # procgen rules run by default on generated plans; they carry no score weight
        # (scores stay comparable) but their errors still force at least ``repair``.
        from skeleton.forge.ai_builder.procgen.checks import check_procgen  # local: procgen imports scoring
        problems.extend(check_procgen(plan))
    return problems


def score_plan(plan: Any, thresholds: Thresholds = Thresholds()) -> Verdict:
    problems = validate_plan(plan)
    by_rule: dict[str, float] = {}
    for rule, weight in WEIGHTS.items():
        mine = [p for p in problems if p.rule == rule]
        loss = sum(thresholds.error_penalty if p.severity is Severity.ERROR else thresholds.warning_penalty
                   for p in mine)
        by_rule[rule] = round(weight * max(0.0, 1.0 - loss), 6)
    score = sum(by_rule.values())
    has_error = any(p.severity is Severity.ERROR for p in problems)
    if any(p.rule in FATAL_RULES and p.severity is Severity.ERROR for p in problems) or score < thresholds.repair:
        verdict = REGENERATE
    elif has_error or score < thresholds.accept:
        verdict = REPAIR
    else:
        verdict = ACCEPT
    return Verdict(verdict, score, tuple(problems), by_rule)

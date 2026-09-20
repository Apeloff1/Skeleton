"""Typed change-intent contracts for autonomous repository work."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Iterable

from .budgets import derive_zone_budgets
from .impact import analyze_impact
from .model import RepositoryModel
from .policy import evaluate_change_policy

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{2,191}$")
_ALLOWED_LANES = {
    "repair",
    "security",
    "regression",
    "integration",
    "architecture",
    "organization",
    "documentation",
    "performance",
    "dependency",
    "build",
}


@dataclass(frozen=True, slots=True)
class ChangeIntent:
    identity: str
    lane: str
    objective: str
    paths: tuple[str, ...]
    expected_checks: tuple[str, ...] = ()
    issue_number: int | None = None
    root_cause_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.identity, str) or _ID_RE.fullmatch(self.identity) is None:
            raise ValueError("identity must be a canonical machine token")
        if self.lane not in _ALLOWED_LANES:
            raise ValueError("unsupported change lane")
        if not isinstance(self.objective, str) or not self.objective.strip():
            raise ValueError("objective must not be empty")
        if len(self.objective) > 2000:
            raise ValueError("objective exceeds maximum length")
        canonical: list[str] = []
        for path in self.paths:
            if not isinstance(path, str) or not path:
                raise ValueError("intent paths must be non-empty strings")
            normalized = path.replace("\\", "/").lstrip("./")
            pure = PurePosixPath(normalized)
            if pure.is_absolute() or ".." in pure.parts:
                raise ValueError("intent paths must be repository relative")
            canonical.append(normalized)
        object.__setattr__(self, "paths", tuple(sorted(set(canonical))))
        checks = tuple(sorted({str(item).strip() for item in self.expected_checks if str(item).strip()}))
        object.__setattr__(self, "expected_checks", checks)
        roots = tuple(sorted({str(item).strip() for item in self.root_cause_ids if str(item).strip()}))
        object.__setattr__(self, "root_cause_ids", roots)
        if self.issue_number is not None:
            if isinstance(self.issue_number, bool) or not isinstance(self.issue_number, int) or self.issue_number < 1:
                raise ValueError("issue_number must be positive when provided")

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "lane": self.lane,
            "objective": self.objective,
            "paths": list(self.paths),
            "expected_checks": list(self.expected_checks),
            "issue_number": self.issue_number,
            "root_cause_ids": list(self.root_cause_ids),
        }


@dataclass(frozen=True, slots=True)
class IntentAssessment:
    allowed: bool
    risk: str
    touched_zones: tuple[str, ...]
    required_checks: tuple[str, ...]
    budget_violations: tuple[str, ...]
    policy_violations: tuple[str, ...]
    advisories: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "risk": self.risk,
            "touched_zones": list(self.touched_zones),
            "required_checks": list(self.required_checks),
            "budget_violations": list(self.budget_violations),
            "policy_violations": list(self.policy_violations),
            "advisories": list(self.advisories),
        }


def assess_change_intent(
    model: RepositoryModel,
    intent: ChangeIntent,
    *,
    estimated_changed_lines: int = 0,
) -> IntentAssessment:
    if isinstance(estimated_changed_lines, bool) or not isinstance(estimated_changed_lines, int) or estimated_changed_lines < 0:
        raise ValueError("estimated_changed_lines must be non-negative")
    impact = analyze_impact(model, intent.paths)
    policy = evaluate_change_policy(model, intent.paths)
    budgets = {item.zone: item for item in derive_zone_budgets(model)}
    budget_violations: list[str] = []
    advisories: list[str] = list(policy.advisory)

    paths_by_zone: dict[str, int] = {}
    file_zone = {item.path: item.zone for item in model.files}
    for path in intent.paths:
        zone = file_zone.get(path, "unclassified")
        paths_by_zone[zone] = paths_by_zone.get(zone, 0) + 1

    for zone, count in sorted(paths_by_zone.items()):
        budget = budgets.get(zone)
        if budget is None:
            advisories.append(f"no explicit machine budget available for zone {zone}")
            continue
        if count > budget.max_changed_files:
            budget_violations.append(
                f"{zone}: {count} changed paths exceeds file budget {budget.max_changed_files}"
            )
        if estimated_changed_lines and estimated_changed_lines > budget.max_changed_lines and len(paths_by_zone) == 1:
            budget_violations.append(
                f"{zone}: estimated lines {estimated_changed_lines} exceeds line budget {budget.max_changed_lines}"
            )

    required = set(policy.required_checks)
    required.update(intent.expected_checks)
    if intent.lane == "security":
        required.update({"secret-scanning", "malware-gate"})
    if intent.lane in {"architecture", "organization"}:
        required.add("repository-machine-contract")
    if intent.lane == "regression":
        required.add("python-unit")

    if impact.risk_score >= 45 and not intent.paths:
        budget_violations.append("elevated-risk change intent must declare affected paths")

    return IntentAssessment(
        allowed=policy.allowed and not budget_violations,
        risk=policy.risk,
        touched_zones=impact.touched_zones,
        required_checks=tuple(sorted(required)),
        budget_violations=tuple(budget_violations),
        policy_violations=policy.violations,
        advisories=tuple(sorted(set(advisories))),
    )


def intents_conflict(left: ChangeIntent, right: ChangeIntent, model: RepositoryModel) -> bool:
    if set(left.paths).intersection(right.paths):
        return True
    left_zones = set(analyze_impact(model, left.paths).touched_zones)
    right_zones = set(analyze_impact(model, right.paths).touched_zones)
    if left_zones.intersection(right_zones):
        return True
    if left.lane == right.lane and left.lane in {"architecture", "security", "integration"}:
        return True
    return False


def filter_non_conflicting_intents(
    model: RepositoryModel,
    intents: Iterable[ChangeIntent],
    *,
    limit: int = 8,
) -> tuple[ChangeIntent, ...]:
    selected: list[ChangeIntent] = []
    for intent in intents:
        assessment = assess_change_intent(model, intent)
        if not assessment.allowed:
            continue
        if any(intents_conflict(intent, existing, model) for existing in selected):
            continue
        selected.append(intent)
        if len(selected) >= limit:
            break
    return tuple(selected)

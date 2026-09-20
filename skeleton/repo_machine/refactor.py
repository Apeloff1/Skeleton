"""Evidence-backed refactor planning for machine-selected repository hotspots.

Plans are advisory data. This module never edits files. It translates structural
signals into bounded refactor envelopes that the normal mutation authority can
review, test and execute.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

from .budgets import derive_zone_budgets
from .hotspots import Hotspot, structural_hotspots
from .model import RepositoryModel
from .test_affinity import build_test_affinity


@dataclass(frozen=True, slots=True)
class RefactorStep:
    order: int
    action: str
    source_path: str
    target_hint: str
    validation: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "order": self.order,
            "action": self.action,
            "source_path": self.source_path,
            "target_hint": self.target_hint,
            "validation": list(self.validation),
        }


@dataclass(frozen=True, slots=True)
class RefactorPlan:
    identity: str
    zone: str
    source_path: str
    priority: int
    rationale: tuple[str, ...]
    steps: tuple[RefactorStep, ...]
    related_tests: tuple[str, ...]
    max_changed_files: int
    max_changed_lines: int
    constraints: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "zone": self.zone,
            "source_path": self.source_path,
            "priority": self.priority,
            "rationale": list(self.rationale),
            "steps": [item.as_dict() for item in self.steps],
            "related_tests": list(self.related_tests),
            "max_changed_files": self.max_changed_files,
            "max_changed_lines": self.max_changed_lines,
            "constraints": list(self.constraints),
        }


def _target_hint(path: str, index: int) -> str:
    pure = PurePosixPath(path)
    stem = pure.stem
    parent = pure.parent.as_posix()
    suffix = pure.suffix or ".py"
    name = f"{stem}_{'core' if index == 1 else 'support'}{suffix}"
    return f"{parent}/{name}" if parent != "." else name


def plan_refactors(
    model: RepositoryModel,
    *,
    minimum_hotspot_score: int = 45,
    limit: int = 24,
) -> tuple[RefactorPlan, ...]:
    budgets = {item.zone: item for item in derive_zone_budgets(model)}
    affinity = build_test_affinity(model, minimum_score=20, max_tests_per_source=8)
    hotspots = [
        item for item in structural_hotspots(model, limit=256)
        if item.scope == "file" and item.score >= minimum_hotspot_score
    ]
    plans: list[RefactorPlan] = []
    for hotspot in hotspots:
        budget = budgets.get(hotspot.zone)
        if budget is None:
            continue
        tests = tuple(
            match.test_path
            for match in affinity.get(hotspot.path, ())
        )
        validation = tests or ("machine:derive-focused-tests",)
        steps = (
            RefactorStep(
                order=1,
                action="characterize",
                source_path=hotspot.path,
                target_hint="",
                validation=validation,
            ),
            RefactorStep(
                order=2,
                action="extract-cohesive-boundary",
                source_path=hotspot.path,
                target_hint=_target_hint(hotspot.path, 1),
                validation=validation,
            ),
            RefactorStep(
                order=3,
                action="extract-supporting-boundary",
                source_path=hotspot.path,
                target_hint=_target_hint(hotspot.path, 2),
                validation=validation,
            ),
            RefactorStep(
                order=4,
                action="preserve-compatibility-surface",
                source_path=hotspot.path,
                target_hint="",
                validation=validation,
            ),
            RefactorStep(
                order=5,
                action="validate-and-remove-dead-internals",
                source_path=hotspot.path,
                target_hint="",
                validation=validation,
            ),
        )
        plans.append(RefactorPlan(
            identity=f"refactor:{hotspot.path}",
            zone=hotspot.zone,
            source_path=hotspot.path,
            priority=min(100, 40 + hotspot.score),
            rationale=hotspot.reasons,
            steps=steps,
            related_tests=tests,
            max_changed_files=budget.max_changed_files,
            max_changed_lines=budget.max_changed_lines,
            constraints=(
                "preserve public behavior and import compatibility",
                "do not combine unrelated cleanup with the extraction",
                "add characterization coverage before deleting behavior",
                "remain within the machine zone mutation budget",
                "recompute topology and test affinity after each landed slice",
            ),
        ))
    plans.sort(key=lambda item: (-item.priority, item.zone, item.source_path))
    return tuple(plans[:limit])


def refactor_paths(plans: Iterable[RefactorPlan]) -> tuple[str, ...]:
    return tuple(sorted({
        plan.source_path
        for plan in plans
    }))

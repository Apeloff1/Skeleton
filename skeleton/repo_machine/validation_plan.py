"""Derive focused validation targets for a typed change intent."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from .impact import analyze_impact
from .intent import ChangeIntent, assess_change_intent
from .model import RepositoryModel
from .test_affinity import build_test_affinity


@dataclass(frozen=True, slots=True)
class ValidationTarget:
    kind: str
    value: str
    reason: str
    required: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "value": self.value,
            "reason": self.reason,
            "required": self.required,
        }


@dataclass(frozen=True, slots=True)
class ValidationPlan:
    intent_id: str
    risk: str
    targets: tuple[ValidationTarget, ...]
    uncovered_changed_sources: tuple[str, ...]
    affected_zones: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "intent_id": self.intent_id,
            "risk": self.risk,
            "targets": [item.as_dict() for item in self.targets],
            "uncovered_changed_sources": list(self.uncovered_changed_sources),
            "affected_zones": list(self.affected_zones),
        }


def build_validation_plan(
    model: RepositoryModel,
    intent: ChangeIntent,
) -> ValidationPlan:
    assessment = assess_change_intent(model, intent)
    impact = analyze_impact(model, intent.paths)
    affinity = build_test_affinity(model)
    records = {item.path: item for item in model.files}
    targets: list[ValidationTarget] = []
    seen: set[tuple[str, str]] = set()
    uncovered: list[str] = []

    def add(kind: str, value: str, reason: str, required: bool = True) -> None:
        key = (kind, value)
        if key in seen:
            return
        seen.add(key)
        targets.append(ValidationTarget(kind, value, reason, required))

    for check in assessment.required_checks:
        add("check", check, "required by machine change policy")

    for path in intent.paths:
        record = records.get(path)
        if record is None or record.kind != "source":
            continue
        matches = affinity.get(path, ())
        if not matches:
            uncovered.append(path)
            add(
                "test-gap",
                path,
                "changed source has no high-confidence mapped regression test",
            )
        else:
            for match in matches[:5]:
                add(
                    "test-file",
                    match.test_path,
                    f"affinity={match.score} for changed source {path}",
                )

    if impact.critical_zones:
        add(
            "suite",
            "integration-smoke",
            "change reaches high/critical subsystem",
        )
    if any(path.startswith(".github/workflows/") for path in intent.paths):
        add(
            "suite",
            "workflow-contracts",
            "change touches GitHub Actions control plane",
        )
    if any(PurePosixPath(path).suffix.casefold() in {".toml", ".yaml", ".yml"} for path in intent.paths):
        add(
            "suite",
            "configuration-contracts",
            "change modifies repository configuration",
            required=assessment.risk in {"high", "critical"},
        )

    targets.sort(key=lambda item: (not item.required, item.kind, item.value))
    return ValidationPlan(
        intent_id=intent.identity,
        risk=assessment.risk,
        targets=tuple(targets),
        uncovered_changed_sources=tuple(sorted(set(uncovered))),
        affected_zones=impact.touched_zones,
    )

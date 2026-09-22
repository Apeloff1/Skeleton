"""Machine-organization policy checks for proposed repository changes."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

from .impact import analyze_impact
from .model import RepositoryModel


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    risk: str
    required_checks: tuple[str, ...]
    violations: tuple[str, ...]
    advisory: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "risk": self.risk,
            "required_checks": list(self.required_checks),
            "violations": list(self.violations),
            "advisory": list(self.advisory),
        }


def _risk(score: int) -> str:
    if score >= 70:
        return "critical"
    if score >= 45:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


def evaluate_change_policy(
    model: RepositoryModel,
    changed_paths: Iterable[str],
) -> PolicyDecision:
    impact = analyze_impact(model, changed_paths)
    paths = impact.changed_paths
    violations: list[str] = []
    advisory: list[str] = []
    checks: set[str] = {"repository-machine-contract"}

    if any(path.startswith(".machine/") for path in paths):
        checks.add("workflow-input-security")
        advisory.append("machine topology contract changed; inspect generated context diff")
    if any(path.startswith(".github/workflows/") for path in paths):
        checks.update({"workflow-input-security", "merge-readiness"})
        advisory.append("workflow control-plane change requires exact-head validation")
    if any(path.startswith(("skeleton/automation/", "skeleton/repo_machine/")) for path in paths):
        checks.update({"pr-automation-tests", "merge-readiness"})
    if any(PurePosixPath(path).suffix.casefold() == ".py" for path in paths):
        checks.add("python-unit")
    if impact.critical_zones:
        checks.add("integration-smoke")
    if impact.risk_score >= 70 and not any("test" in PurePosixPath(path).name.casefold() for path in paths):
        advisory.append("high blast-radius change contains no explicit test-file modification")

    for path in paths:
        if path.startswith((".git/", "node_modules/", ".venv/")):
            violations.append(f"forbidden machine-managed path: {path}")
        if ".." in PurePosixPath(path).parts:
            violations.append(f"non-canonical path traversal: {path}")

    if model.truncated:
        violations.append("repository machine model is truncated; fail closed for mutation planning")
    if model.unclassified_count > max(500, len(model.files) // 2):
        advisory.append("large unclassified surface weakens machine ownership precision")

    return PolicyDecision(
        allowed=not violations,
        risk=_risk(impact.risk_score),
        required_checks=tuple(sorted(checks)),
        violations=tuple(sorted(set(violations))),
        advisory=tuple(sorted(set(advisory))),
    )

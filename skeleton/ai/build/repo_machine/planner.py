"""Convert repository organization findings into bounded machine work candidates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .model import Finding, RepositoryModel

_SEVERITY = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
_CODE_WEIGHT = {
    "scan.truncated": 50,
    "scan.unreadable": 45,
    "topology.cycle": 40,
    "quality.missing-zone-tests": 35,
    "organization.oversized-module": 25,
    "organization.unclassified": 10,
}


@dataclass(frozen=True, slots=True)
class WorkCandidate:
    identity: str
    lane: str
    priority: int
    zone: str
    path: str
    objective: str
    evidence: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "lane": self.lane,
            "priority": self.priority,
            "zone": self.zone,
            "path": self.path,
            "objective": self.objective,
            "evidence": list(self.evidence),
        }


def _lane(finding: Finding) -> str:
    if finding.code.startswith("quality."):
        return "regression"
    if finding.code.startswith("topology."):
        return "architecture"
    if finding.code.startswith("scan."):
        return "repository-health"
    return "organization"


def _objective(finding: Finding) -> str:
    mapping = {
        "topology.cycle": "Break the cross-subsystem dependency cycle with the smallest stable boundary.",
        "quality.missing-zone-tests": "Add focused regression coverage for this code-bearing subsystem.",
        "organization.oversized-module": "Split the oversized module along existing cohesive boundaries without changing behavior.",
        "organization.unclassified": "Classify this path into the canonical machine repository map or add a justified zone.",
        "scan.truncated": "Reduce machine-index breadth or raise the bounded capacity with explicit validation.",
        "scan.unreadable": "Restore deterministic machine readability for this repository path.",
    }
    return mapping.get(finding.code, finding.detail or finding.code)


def derive_work_candidates(
    model: RepositoryModel,
    *,
    limit: int = 64,
) -> tuple[WorkCandidate, ...]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 512:
        raise ValueError("limit must be in [1,512]")
    candidates: list[WorkCandidate] = []
    for finding in model.findings:
        score = _SEVERITY[finding.severity] * 100 + _CODE_WEIGHT.get(finding.code, 0)
        candidates.append(WorkCandidate(
            identity=finding.identity,
            lane=_lane(finding),
            priority=score,
            zone=finding.zone,
            path=finding.path,
            objective=_objective(finding),
            evidence=finding.evidence,
        ))
    candidates.sort(key=lambda item: (-item.priority, item.zone, item.path, item.identity))
    return tuple(candidates[:limit])


def candidate_payload(model: RepositoryModel, *, limit: int = 24) -> dict[str, object]:
    return {
        "repository_fingerprint": model.fingerprint,
        "work": [item.as_dict() for item in derive_work_candidates(model, limit=limit)],
    }

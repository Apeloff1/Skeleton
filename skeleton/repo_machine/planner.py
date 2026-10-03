"""Dependency-aware bounded work planning for autonomous repository agents."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .impact import analyze_impact
from .model import Finding, RepositoryModel

_SEVERITY = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
_CODE_WEIGHT = {
    "scan.truncated": 50, "scan.unreadable": 45, "topology.cycle": 40,
    "quality.missing-zone-tests": 35, "organization.oversized-module": 25,
    "organization.unclassified": 10,
}
_LANE_WEIGHT = {"repository-health": 30, "architecture": 20, "regression": 15, "organization": 5}


@dataclass(frozen=True, slots=True)
class WorkCandidate:
    identity: str
    lane: str
    priority: int
    zone: str
    path: str
    objective: str
    evidence: tuple[str, ...]
    impact_score: int = 0
    change_class: str = "unknown"
    verification_paths: tuple[str, ...] = ()
    dependency_zones: tuple[str, ...] = ()
    prerequisite_ids: tuple[str, ...] = ()
    readiness: str = "ready"

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity, "lane": self.lane, "priority": self.priority,
            "zone": self.zone, "path": self.path, "objective": self.objective,
            "evidence": list(self.evidence), "impact_score": self.impact_score,
            "change_class": self.change_class, "verification_paths": list(self.verification_paths),
            "dependency_zones": list(self.dependency_zones),
            "prerequisite_ids": list(self.prerequisite_ids),
            "readiness": self.readiness,
        }


def _lane(finding: Finding) -> str:
    if finding.code.startswith("quality."): return "regression"
    if finding.code.startswith("topology."): return "architecture"
    if finding.code.startswith("scan."): return "repository-health"
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


def derive_work_candidates(model: RepositoryModel, *, limit: int = 64) -> tuple[WorkCandidate, ...]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 512:
        raise ValueError("limit must be in [1,512]")
    raw: list[tuple[Finding, int, object]] = []
    for finding in model.findings:
        base = _SEVERITY[finding.severity] * 100 + _CODE_WEIGHT.get(finding.code, 0)
        impact = analyze_impact(model, (finding.path,), transitive_depth=3) if finding.path else None
        impact_score = impact.risk_score if impact else 0
        priority = min(500, base + impact_score + _LANE_WEIGHT.get(_lane(finding), 0))
        raw.append((finding, priority, impact))

    # Higher-priority work becomes a prerequisite when it shares a zone or
    # reaches the same dependency surface. This makes readiness explicit.
    raw.sort(key=lambda item: (-item[1], item[0].zone, item[0].path, item[0].identity))
    candidates: list[WorkCandidate] = []
    for index, (finding, priority, impact) in enumerate(raw):
        prerequisites: set[str] = set()
        if impact:
            affected = set(impact.transitively_affected_zones) | set(impact.touched_zones)
            for previous_finding, previous_priority, previous_impact in raw[:index]:
                if previous_priority <= priority:
                    break
                previous_zones = {previous_finding.zone}
                if previous_impact:
                    previous_zones |= set(previous_impact.transitively_affected_zones)
                if affected & previous_zones:
                    prerequisites.add(previous_finding.identity)
                    break
        candidates.append(WorkCandidate(
            identity=finding.identity, lane=_lane(finding), priority=priority,
            zone=finding.zone, path=finding.path, objective=_objective(finding),
            evidence=tuple(sorted(set(finding.evidence + (impact.reasons if impact else ())))),
            impact_score=impact.risk_score if impact else 0,
            change_class=impact.change_class if impact else "unknown",
            verification_paths=impact.verification_paths if impact else (),
            dependency_zones=tuple(sorted(set(impact.transitively_affected_zones) - set(impact.touched_zones))) if impact else (),
            prerequisite_ids=tuple(sorted(prerequisites)),
            readiness="ready" if not prerequisites else "gated",
        ))
    candidates.sort(key=lambda item: (-item.priority, -item.impact_score, item.zone, item.path, item.identity))
    return tuple(candidates[:limit])


def plan_work(model: RepositoryModel, *, limit: int = 24) -> dict[str, object]:
    candidates = derive_work_candidates(model, limit=limit)
    return {
        "repository_fingerprint": model.fingerprint,
        "planning_model": "severity + lane weight + bounded topology impact + readiness gates",
        "work": [item.as_dict() for item in candidates],
    }


def candidate_payload(model: RepositoryModel, *, limit: int = 24) -> dict[str, object]:
    return plan_work(model, limit=limit)

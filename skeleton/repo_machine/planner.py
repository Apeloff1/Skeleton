"""Dependency-aware bounded work planning for autonomous repository agents."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .impact import ImpactReport, analyze_impact
from .model import Finding, RepositoryModel

_SEVERITY = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
_CODE_WEIGHT = {"scan.truncated": 50, "scan.unreadable": 45, "topology.cycle": 40,
                "quality.missing-zone-tests": 35, "organization.oversized-module": 25,
                "organization.unclassified": 10}
_LANE_WEIGHT = {"repository-health": 30, "architecture": 20, "regression": 15, "organization": 5}
_MAX_PREREQUISITES = 3


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
    prerequisite_reasons: tuple[str, ...] = ()
    readiness: str = "ready"
    decision_score: int = 0
    topology_confidence: int = 0
    blast_radius: int = 0
    verification_depth: int = 0

    def as_dict(self) -> dict[str, object]:
        return {"identity": self.identity, "lane": self.lane, "priority": self.priority,
                "zone": self.zone, "path": self.path, "objective": self.objective,
                "evidence": list(self.evidence), "impact_score": self.impact_score,
                "change_class": self.change_class, "verification_paths": list(self.verification_paths),
                "dependency_zones": list(self.dependency_zones),
                "prerequisite_ids": list(self.prerequisite_ids),
                "prerequisite_reasons": list(self.prerequisite_reasons),
                "readiness": self.readiness, "decision_score": self.decision_score,
                "topology_confidence": self.topology_confidence, "blast_radius": self.blast_radius,
                "verification_depth": self.verification_depth}


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


def _gate_reason(gate: Finding, gate_priority: int, candidate: Finding, candidate_priority: int,
                 shared_zones: tuple[str, ...]) -> str:
    return (f"{gate.identity} gates {candidate.identity}: higher-priority {gate.code} "
            f"({gate_priority}>{candidate_priority}) overlaps {','.join(shared_zones)}")


def _impact_priority(impact: ImpactReport | None) -> int:
    if impact is None:
        return 0
    # Confidence prevents sparse topology from dominating. Blast radius is
    # logarithmically bounded by the fixed multiplier and final priority cap.
    confidence = impact.topology_confidence // 10
    radius = min(20, impact.blast_radius * 2)
    return impact.risk_score + confidence + radius


def derive_work_candidates(model: RepositoryModel, *, limit: int = 64) -> tuple[WorkCandidate, ...]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 512:
        raise ValueError("limit must be in [1,512]")
    raw: list[tuple[Finding, int, ImpactReport | None]] = []
    for finding in model.findings:
        impact = analyze_impact(model, (finding.path,), transitive_depth=3) if finding.path else None
        base = _SEVERITY[finding.severity] * 100 + _CODE_WEIGHT.get(finding.code, 0)
        priority = min(500, base + _LANE_WEIGHT.get(_lane(finding), 0) + _impact_priority(impact))
        raw.append((finding, priority, impact))

    raw.sort(key=lambda item: (-item[1], item[0].zone, item[0].path, item[0].identity))
    zone_gates: dict[str, list[tuple[str, int]]] = {}
    finding_by_id = {finding.identity: finding for finding, _, _ in raw}
    priority_by_id = {finding.identity: priority for finding, priority, _ in raw}
    for finding, priority, impact in raw:
        zones = {finding.zone}
        if impact:
            zones.update(impact.transitively_affected_zones)
            zones.update(impact.touched_zones)
        for zone in zones:
            gates = zone_gates.setdefault(zone, [])
            gates.append((finding.identity, priority))
            gates.sort(key=lambda item: (-item[1], item[0]))
            del gates[_MAX_PREREQUISITES:]

    candidates: list[WorkCandidate] = []
    for finding, priority, impact in raw:
        affected = set(impact.transitively_affected_zones) | set(impact.touched_zones) if impact else {finding.zone}
        gate_map: dict[str, set[str]] = {}
        for zone in affected:
            for identity, gate_priority in zone_gates.get(zone, ()):
                if identity == finding.identity or gate_priority <= priority:
                    continue
                gate_map.setdefault(identity, set()).add(zone)
        ranked_gates = sorted(
            ((identity, zones, priority_by_id[identity]) for identity, zones in gate_map.items()),
            key=lambda item: (-item[2], item[0]),
        )[:_MAX_PREREQUISITES]
        prerequisites = tuple(sorted(identity for identity, _, _ in ranked_gates))
        reasons = tuple(_gate_reason(finding_by_id[identity], gate_priority, finding, priority,
                                     tuple(sorted(zones)))
                        for identity, zones, gate_priority in ranked_gates)
        decision_score = min(100, priority // 5)
        candidates.append(WorkCandidate(
            identity=finding.identity, lane=_lane(finding), priority=priority,
            zone=finding.zone, path=finding.path, objective=_objective(finding),
            evidence=tuple(sorted(set(finding.evidence + (impact.reasons if impact else ())))),
            impact_score=impact.risk_score if impact else 0,
            change_class=impact.change_class if impact else "unknown",
            verification_paths=impact.verification_paths if impact else (),
            dependency_zones=tuple(sorted(set(impact.transitively_affected_zones) - set(impact.touched_zones))) if impact else (),
            prerequisite_ids=prerequisites, prerequisite_reasons=reasons,
            readiness="ready" if not prerequisites else "gated",
            decision_score=decision_score,
            topology_confidence=impact.topology_confidence if impact else 0,
            blast_radius=impact.blast_radius if impact else 0,
            verification_depth=impact.recommended_depth if impact else 0,
        ))
    candidates.sort(key=lambda item: (-item.decision_score, -item.impact_score, item.zone, item.path, item.identity))
    return tuple(candidates[:limit])


def plan_work(model: RepositoryModel, *, limit: int = 24) -> dict[str, object]:
    candidates = derive_work_candidates(model, limit=limit)
    return {"repository_fingerprint": model.fingerprint,
            "planning_model": "severity + lane + risk + topology confidence + bounded blast radius + multi-gate evidence",
            "work": [item.as_dict() for item in candidates]}


def candidate_payload(model: RepositoryModel, *, limit: int = 24) -> dict[str, object]:
    return plan_work(model, limit=limit)

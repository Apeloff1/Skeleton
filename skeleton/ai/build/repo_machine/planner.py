"""Dependency-aware bounded work planning for autonomous repository agents."""
from __future__ import annotations

from dataclasses import dataclass

from .impact import ImpactReport, analyze_impact
from .model import Finding, RepositoryModel

_SEVERITY = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
_CODE_WEIGHT = {"scan.truncated": 50, "scan.unreadable": 45, "topology.cycle": 40,
                "quality.missing-zone-tests": 35, "organization.oversized-module": 25,
                "organization.unclassified": 10}
_LANE_WEIGHT = {"repository-health": 30, "architecture": 20, "regression": 15, "organization": 5}
_CRITICALITY_WEIGHT = {"critical": 24, "high": 16, "medium": 8, "low": 2}
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
    decision_reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {"identity": self.identity, "lane": self.lane, "priority": self.priority, "zone": self.zone,
                "path": self.path, "objective": self.objective, "evidence": list(self.evidence),
                "impact_score": self.impact_score, "change_class": self.change_class,
                "verification_paths": list(self.verification_paths), "dependency_zones": list(self.dependency_zones),
                "prerequisite_ids": list(self.prerequisite_ids), "prerequisite_reasons": list(self.prerequisite_reasons),
                "readiness": self.readiness, "decision_score": self.decision_score,
                "topology_confidence": self.topology_confidence, "blast_radius": self.blast_radius,
                "verification_depth": self.verification_depth, "decision_reasons": list(self.decision_reasons)}

def _normalize_finding_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


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

def _gate_reason(gate: Finding, gate_priority: int, candidate: Finding, candidate_priority: int, shared_zones: tuple[str, ...]) -> str:
    return (f"{gate.identity} gates {candidate.identity}: higher-priority {gate.code} "
            f"({gate_priority}>{candidate_priority}) overlaps {','.join(shared_zones)}")

def _impact_priority(impact: ImpactReport | None) -> int:
    if impact is None: return 0
    return (impact.risk_score + impact.topology_confidence // 10 +
            min(20, impact.weighted_blast_radius // 4) +
            min(12, impact.criticality_weighted_blast_radius // 8) +
            min(8, impact.independent_path_count * 2) +
            min(10, impact.max_dependency_depth * 2))

def _decision_factors(finding: Finding, impact: ImpactReport | None, model: RepositoryModel) -> tuple[int, tuple[str, ...]]:
    subsystem = next((item for item in model.subsystems if item.name == finding.zone), None)
    criticality = subsystem.criticality if subsystem else "medium"
    score = _CRITICALITY_WEIGHT.get(criticality, 0)
    reasons = [f"zone criticality={criticality}"]
    if finding.severity in {"critical", "high"}: reasons.append(f"finding severity={finding.severity}")
    if impact:
        if impact.blast_radius >= 4: reasons.append(f"blast radius={impact.blast_radius}")
        if impact.criticality_weighted_blast_radius >= 20:
            score += min(12, impact.criticality_weighted_blast_radius // 10)
            reasons.append(f"criticality-weighted blast={impact.criticality_weighted_blast_radius}")
        if impact.independent_path_count >= 2:
            score += min(8, impact.independent_path_count * 2)
            reasons.append(f"independent topology paths={impact.independent_path_count}")
        if impact.reachability_confidence < 40:
            score -= 4
            reasons.append("weak reachability evidence reduces confidence")
        elif impact.reachability_confidence >= 80:
            score += 4
            reasons.append("strong reachability evidence")
        if impact.max_dependency_depth >= 3:
            score += 5
            reasons.append(f"deep dependency propagation={impact.max_dependency_depth}")
    if finding.code == "quality.missing-zone-tests" and (subsystem.test_surface_count if subsystem else 0) == 0:
        score += 12
        reasons.append("no known test surface")
    if impact and impact.change_class == "control-plane":
        score += 10
        reasons.append("control-plane change")
    return score, tuple(reasons)

def _decision_score(finding: Finding, impact: ImpactReport | None, decision_bonus: int) -> int:
    severity_component = _SEVERITY[finding.severity] * 12
    risk_component = min(25, impact.risk_score // 4) if impact else 0
    confidence_component = min(15, (impact.reachability_confidence if impact else 0) // 7)
    criticality_component = min(15, decision_bonus)
    blast_component = min(18, (impact.criticality_weighted_blast_radius if impact else 0) // 6)
    path_component = min(8, (impact.independent_path_count if impact else 0) * 2)
    depth_component = min(10, (impact.max_dependency_depth if impact else 0) * 3)
    return min(100, max(0, severity_component + risk_component + confidence_component +
                         criticality_component + blast_component + path_component + depth_component))

def _normalize_finding_path(path: str) -> str:
    """Normalize repository finding paths to stable forward-slash form."""

    return path.replace("\\", "/").lstrip("./")


def derive_work_candidates(model: RepositoryModel, *, limit: int = 64) -> tuple[WorkCandidate, ...]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 512:
        raise ValueError("limit must be in [1,512]")
    impact_cache: dict[str, ImpactReport] = {}
    raw = []
    for finding in model.findings:
        impact = None
        if finding.path:
            key = _normalize_finding_path(finding.path)
            impact = impact_cache.get(key)
            if impact is None:
                impact = analyze_impact(model, (key,), transitive_depth=3)
                impact_cache[key] = impact
        decision_bonus, decision_reasons = _decision_factors(finding, impact, model)
        priority = min(500, _SEVERITY[finding.severity] * 100 + _CODE_WEIGHT.get(finding.code, 0) +
                       _LANE_WEIGHT.get(_lane(finding), 0) + _impact_priority(impact) + decision_bonus)
        raw.append((finding, priority, impact, decision_reasons, _decision_score(finding, impact, decision_bonus)))

    raw.sort(key=lambda item: (-item[4], -item[1], item[0].zone, item[0].path, item[0].identity))
    zone_gates: dict[str, list[tuple[str, int]]] = {}
    finding_by_id = {f.identity: f for f, _, _, _, _ in raw}
    priority_by_id = {f.identity: p for f, p, _, _, _ in raw}
    for finding, priority, impact, _, _ in raw:
        zones = {finding.zone}
        if impact: zones.update(impact.transitively_affected_zones); zones.update(impact.touched_zones)
        for zone in zones:
            gates = zone_gates.setdefault(zone, [])
            gates.append((finding.identity, priority))
            gates.sort(key=lambda item: (-item[1], item[0]))
            del gates[_MAX_PREREQUISITES:]

    candidates = []
    for finding, priority, impact, decision_reasons, score in raw:
        affected = set(impact.transitively_affected_zones) | set(impact.touched_zones) if impact else {finding.zone}
        gate_map: dict[str, set[str]] = {}
        for zone in affected:
            for identity, gate_priority in zone_gates.get(zone, ()):
                if identity != finding.identity and gate_priority > priority:
                    gate_map.setdefault(identity, set()).add(zone)
        ranked = sorted(((i, z, priority_by_id[i]) for i, z in gate_map.items()),
                        key=lambda item: (-item[2], item[0]))[:_MAX_PREREQUISITES]
        prerequisites = tuple(sorted(i for i, _, _ in ranked))
        reasons = tuple(_gate_reason(finding_by_id[i], p, finding, priority, tuple(sorted(z)))
                        for i, z, p in ranked)
        candidates.append(WorkCandidate(
            identity=finding.identity, lane=_lane(finding), priority=priority, zone=finding.zone, path=finding.path,
            objective=_objective(finding), evidence=tuple(sorted(set(finding.evidence + (impact.reasons if impact else ())))),
            impact_score=impact.risk_score if impact else 0, change_class=impact.change_class if impact else "unknown",
            verification_paths=impact.verification_paths if impact else (),
            dependency_zones=tuple(sorted(set(impact.transitively_affected_zones) - set(impact.touched_zones))) if impact else (),
            prerequisite_ids=prerequisites, prerequisite_reasons=reasons, readiness="ready" if not prerequisites else "gated",
            decision_score=score, topology_confidence=impact.topology_confidence if impact else 0,
            blast_radius=impact.blast_radius if impact else 0, verification_depth=impact.recommended_depth if impact else 0,
            decision_reasons=decision_reasons))
    candidates.sort(key=lambda item: (-item.decision_score, -item.priority, item.zone, item.path, item.identity))
    return tuple(candidates[:limit])

def plan_work(model: RepositoryModel, *, limit: int = 24) -> dict[str, object]:
    return {"repository_fingerprint": model.fingerprint,
            "planning_model": "severity + lane + criticality + risk + weighted reachability + criticality-weighted blast + path multiplicity + dependency depth + multi-gate evidence",
            "work": [item.as_dict() for item in derive_work_candidates(model, limit=limit)]}

def candidate_payload(model: RepositoryModel, *, limit: int = 24) -> dict[str, object]:
    return plan_work(model, limit=limit)

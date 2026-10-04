"""Impact analysis over the machine repository topology."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

from .model import RepositoryModel


@dataclass(frozen=True, slots=True)
class ImpactReport:
    changed_paths: tuple[str, ...]
    touched_zones: tuple[str, ...]
    directly_affected_zones: tuple[str, ...]
    transitively_affected_zones: tuple[str, ...]
    test_zones: tuple[str, ...]
    critical_zones: tuple[str, ...]
    risk_score: int
    reasons: tuple[str, ...]
    change_class: str
    recommended_depth: int
    verification_paths: tuple[str, ...] = ()
    dependency_zones: tuple[str, ...] = ()
    blast_radius: int = 0
    topology_confidence: int = 0
    weighted_blast_radius: int = 0
    reachability_confidence: int = 0
    max_dependency_depth: int = 0
    criticality_weighted_blast_radius: int = 0
    independent_path_count: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "changed_paths": list(self.changed_paths), "touched_zones": list(self.touched_zones),
            "directly_affected_zones": list(self.directly_affected_zones),
            "transitively_affected_zones": list(self.transitively_affected_zones),
            "test_zones": list(self.test_zones), "critical_zones": list(self.critical_zones),
            "risk_score": self.risk_score, "reasons": list(self.reasons),
            "change_class": self.change_class, "recommended_depth": self.recommended_depth,
            "verification_paths": list(self.verification_paths),
            "dependency_zones": list(self.dependency_zones), "blast_radius": self.blast_radius,
            "topology_confidence": self.topology_confidence,
            "weighted_blast_radius": self.weighted_blast_radius,
            "reachability_confidence": self.reachability_confidence,
            "max_dependency_depth": self.max_dependency_depth,
            "criticality_weighted_blast_radius": self.criticality_weighted_blast_radius,
            "independent_path_count": self.independent_path_count,
        }


def _normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def _zone_for_path(model: RepositoryModel, path: str, exact: dict[str, str] | None = None) -> str:
    normalized = _normalize_path(path)
    if exact is None:
        exact = {item.path: item.zone for item in model.files}
    if normalized in exact:
        return exact[normalized]
    parts = PurePosixPath(normalized).parts
    if not parts:
        return "unclassified"
    for item in model.subsystems:
        if item.name != "unclassified" and parts[0].casefold() == item.name.casefold():
            return item.name
    return "unclassified"


def _criticality_weight(value: str) -> int:
    return {"critical": 5, "high": 4, "medium": 2, "low": 1}.get(value, 1)


def analyze_impact(model: RepositoryModel, changed_paths: Iterable[str], *, transitive_depth: int = 3) -> ImpactReport:
    if isinstance(transitive_depth, bool) or not isinstance(transitive_depth, int) or not 0 <= transitive_depth <= 16:
        raise ValueError("transitive_depth must be in [0,16]")
    paths = tuple(sorted({_normalize_path(str(path)) for path in changed_paths if str(path).strip()}))
    exact = {item.path: item.zone for item in model.files}
    zones = tuple(sorted({_zone_for_path(model, path, exact) for path in paths}))

    reverse: dict[str, set[str]] = defaultdict(set)
    forward: dict[str, set[str]] = defaultdict(set)
    edge_weight: dict[tuple[str, str], int] = {}
    for edge in model.edges:
        reverse[edge.target].add(edge.source)
        forward[edge.source].add(edge.target)
        edge_weight[(edge.source, edge.target)] = max(edge_weight.get((edge.source, edge.target), 0), edge.evidence_count)

    direct: set[str] = set()
    for zone in zones:
        direct.update(reverse.get(zone, ()))

    distances: dict[str, int] = {zone: 0 for zone in zones}
    path_confidence: dict[str, float] = {zone: 1.0 for zone in zones}
    path_counts: dict[str, int] = {zone: 1 for zone in zones}
    frontier = deque(sorted(zones))
    while frontier:
        zone = frontier.popleft()
        depth = distances[zone]
        if depth >= transitive_depth:
            continue
        for dependent in sorted(reverse.get(zone, ())):
            edge = max(1, edge_weight.get((dependent, zone), 1))
            edge_confidence = min(1.0, edge / 5.0)
            confidence = min(path_confidence[zone], edge_confidence)
            new_depth = depth + 1
            if dependent not in distances or new_depth < distances[dependent]:
                distances[dependent] = new_depth
                path_confidence[dependent] = confidence
                path_counts[dependent] = path_counts.get(zone, 1)
                frontier.append(dependent)
            elif new_depth == distances[dependent]:
                path_counts[dependent] = min(100, path_counts.get(dependent, 1) + path_counts.get(zone, 1))
                if confidence > path_confidence[dependent]:
                    path_confidence[dependent] = confidence

    all_affected = set(distances) - set(zones)
    dependency_zones = set()
    for zone in zones:
        dependency_zones.update(forward.get(zone, ()))

    by_name = {item.name: item for item in model.subsystems}
    critical = tuple(sorted(zone for zone in set(zones) | all_affected
                            if zone in by_name and by_name[zone].criticality in {"critical", "high"}))
    verification_zone_set = set(zones) | all_affected | {"tests"}
    verification_paths = tuple(sorted(
        item.path for item in model.files if item.kind == "test" and item.zone in verification_zone_set
    )[:200])
    tests = tuple(sorted({
        item.name for item in model.subsystems
        if item.test_surface_count and item.name in verification_zone_set
    }))

    weighted_blast_radius = min(100, sum(max(1, round(path_confidence[z] * 10)) for z in all_affected))
    criticality_weighted_blast_radius = min(100, sum(
        max(1, round(path_confidence[z] * 10)) * _criticality_weight(by_name[z].criticality)
        for z in all_affected if z in by_name
    ))
    max_dependency_depth = max(distances.values(), default=0)
    reachable = [path_confidence[z] for z in all_affected]
    reachability_confidence = min(100, round((sum(reachable) / len(reachable)) * 100)) if reachable else 100
    topology_confidence = min(100, round(
        (reachability_confidence * 0.55) +
        min(25, weighted_blast_radius) +
        min(20, independent_path_count := sum(max(0, path_counts[z] - 1) for z in all_affected))
    ))

    reasons: list[str] = []
    score = 0
    if "unclassified" in zones:
        score += 15
        reasons.append("change touches unclassified repository surface")
    if critical:
        score += min(50, len(critical) * 12)
        reasons.append("change reaches critical/high subsystems")
    if criticality_weighted_blast_radius >= 40:
        score += min(15, criticality_weighted_blast_radius // 10)
        reasons.append("change has high criticality-weighted blast radius")
    if independent_path_count >= 2:
        score += min(8, independent_path_count)
        reasons.append(f"multiple independent topology paths={independent_path_count}")
    if len(all_affected) > len(zones):
        score += min(25, len(all_affected) * 3)
        reasons.append("change has cross-subsystem dependents")
    if len(dependency_zones) > 1:
        score += min(10, len(dependency_zones) * 2)
        reasons.append("change feeds multiple downstream subsystem directions")
    if weighted_blast_radius >= 40:
        score += min(10, weighted_blast_radius // 10)
        reasons.append("change has a strongly evidenced topology blast radius")
    if max_dependency_depth >= 3:
        score += 5
        reasons.append(f"dependency propagation reaches depth {max_dependency_depth}")
    if reachability_confidence < 50:
        reasons.append("reachable topology has weak edge evidence; prefer conservative verification")
    if len(verification_paths) >= 100:
        reasons.append("verification surface is broad; prefer targeted selection before full suite")
    if any(path.startswith(".github/workflows/") for path in paths):
        score += 20
        reasons.append("change modifies GitHub Actions control plane")
    if any(PurePosixPath(path).suffix.casefold() in {".toml", ".yaml", ".yml", ".json"} for path in paths):
        score += min(15, len(paths) * 2)
        reasons.append("change modifies configuration")
    score = min(score, 100)

    if any(path.startswith(".github/") for path in paths):
        change_class, recommended_depth = "control-plane", min(transitive_depth, 4)
    elif any(PurePosixPath(path).suffix.casefold() in {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java"} for path in paths):
        change_class, recommended_depth = "code", min(transitive_depth, 3)
    elif paths and all(PurePosixPath(path).suffix.casefold() in {".md", ".rst", ".txt"} for path in paths):
        change_class, recommended_depth = "documentation", 1
    else:
        change_class, recommended_depth = "configuration", min(transitive_depth, 2)

    return ImpactReport(
        changed_paths=paths, touched_zones=zones, directly_affected_zones=tuple(sorted(direct)),
        transitively_affected_zones=tuple(sorted(all_affected)), test_zones=tests,
        critical_zones=critical, risk_score=score, reasons=tuple(reasons),
        change_class=change_class, recommended_depth=recommended_depth,
        verification_paths=verification_paths, dependency_zones=tuple(sorted(dependency_zones)),
        blast_radius=len(all_affected), topology_confidence=topology_confidence,
        weighted_blast_radius=weighted_blast_radius,
        reachability_confidence=reachability_confidence,
        max_dependency_depth=max_dependency_depth,
        criticality_weighted_blast_radius=criticality_weighted_blast_radius,
        independent_path_count=independent_path_count,
    )

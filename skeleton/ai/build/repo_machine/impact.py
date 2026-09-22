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

    def as_dict(self) -> dict[str, object]:
        return {
            "changed_paths": list(self.changed_paths),
            "touched_zones": list(self.touched_zones),
            "directly_affected_zones": list(self.directly_affected_zones),
            "transitively_affected_zones": list(self.transitively_affected_zones),
            "test_zones": list(self.test_zones),
            "critical_zones": list(self.critical_zones),
            "risk_score": self.risk_score,
            "reasons": list(self.reasons),
        }


def _normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def _zone_for_path(model: RepositoryModel, path: str) -> str:
    normalized = _normalize_path(path)
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


def analyze_impact(
    model: RepositoryModel,
    changed_paths: Iterable[str],
    *,
    transitive_depth: int = 3,
) -> ImpactReport:
    if isinstance(transitive_depth, bool) or not isinstance(transitive_depth, int) or not 0 <= transitive_depth <= 16:
        raise ValueError("transitive_depth must be in [0,16]")
    paths = tuple(sorted({
        _normalize_path(str(path))
        for path in changed_paths
        if str(path).strip()
    }))
    zones = tuple(sorted({_zone_for_path(model, path) for path in paths}))
    reverse: dict[str, set[str]] = defaultdict(set)
    for edge in model.edges:
        reverse[edge.target].add(edge.source)

    direct: set[str] = set()
    for zone in zones:
        direct.update(reverse.get(zone, ()))

    all_affected = set(direct)
    frontier = deque((zone, 1) for zone in sorted(direct))
    while frontier:
        zone, depth = frontier.popleft()
        if depth >= transitive_depth:
            continue
        for dependent in sorted(reverse.get(zone, ())):
            if dependent in all_affected:
                continue
            all_affected.add(dependent)
            frontier.append((dependent, depth + 1))

    by_name = {item.name: item for item in model.subsystems}
    critical = tuple(sorted(
        zone for zone in set(zones) | all_affected
        if zone in by_name and by_name[zone].criticality in {"critical", "high"}
    ))
    tests = tuple(sorted(
        item.name for item in model.subsystems
        if item.test_files and (
            item.name in zones
            or item.name in all_affected
            or item.name == "tests"
        )
    ))

    reasons: list[str] = []
    score = 0
    if "unclassified" in zones:
        score += 15
        reasons.append("change touches unclassified repository surface")
    if critical:
        score += min(50, len(critical) * 12)
        reasons.append("change reaches critical/high subsystems")
    if len(all_affected) > len(zones):
        score += min(25, len(all_affected) * 3)
        reasons.append("change has cross-subsystem dependents")
    if any(path.startswith(".github/workflows/") for path in paths):
        score += 20
        reasons.append("change modifies GitHub Actions control plane")
    if any(PurePosixPath(path).suffix.casefold() in {".toml", ".yaml", ".yml", ".json"} for path in paths):
        score += min(15, len(paths) * 2)
        reasons.append("change modifies configuration")
    score = min(score, 100)

    return ImpactReport(
        changed_paths=paths,
        touched_zones=zones,
        directly_affected_zones=tuple(sorted(direct)),
        transitively_affected_zones=tuple(sorted(all_affected)),
        test_zones=tests,
        critical_zones=critical,
        risk_score=score,
        reasons=tuple(reasons),
    )

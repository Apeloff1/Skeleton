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
            "change_class": self.change_class,
            "recommended_depth": self.recommended_depth,
            "verification_paths": list(self.verification_paths),
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


def analyze_impact(
    model: RepositoryModel,
    changed_paths: Iterable[str],
    *,
    transitive_depth: int = 3,
) -> ImpactReport:
    if isinstance(transitive_depth, bool) or not isinstance(transitive_depth, int) or not 0 <= transitive_depth <= 16:
        raise ValueError("transitive_depth must be in [0,16]")
    paths = tuple(sorted({_normalize_path(str(path)) for path in changed_paths if str(path).strip()}))
    exact = {item.path: item.zone for item in model.files}
    zones = tuple(sorted({_zone_for_path(model, path, exact) for path in paths}))

    reverse: dict[str, set[str]] = defaultdict(set)
    forward: dict[str, set[str]] = defaultdict(set)
    for edge in model.edges:
        reverse[edge.target].add(edge.source)
        forward[edge.source].add(edge.target)

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
    verification_zone_set = set(zones) | all_affected | {"tests"}
    verification_paths = tuple(sorted(
        item.path for item in model.files
        if item.kind == "test" and item.zone in verification_zone_set
    )[:200])
    tests = tuple(sorted({
        item.name for item in model.subsystems
        if item.test_surface_count and item.name in verification_zone_set
    }))

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
        change_class = "control-plane"
        recommended_depth = min(transitive_depth, 4)
    elif any(PurePosixPath(path).suffix.casefold() in {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java"} for path in paths):
        change_class = "code"
        recommended_depth = min(transitive_depth, 3)
    elif paths and all(PurePosixPath(path).suffix.casefold() in {".md", ".rst", ".txt"} for path in paths):
        change_class = "documentation"
        recommended_depth = 1
    else:
        change_class = "configuration"
        recommended_depth = min(transitive_depth, 2)

    return ImpactReport(
        changed_paths=paths,
        touched_zones=zones,
        directly_affected_zones=tuple(sorted(direct)),
        transitively_affected_zones=tuple(sorted(all_affected)),
        test_zones=tests,
        critical_zones=critical,
        risk_score=score,
        reasons=tuple(reasons),
        change_class=change_class,
        recommended_depth=recommended_depth,
        verification_paths=verification_paths,
    )

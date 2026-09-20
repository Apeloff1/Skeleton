"""Derive machine-readable architectural layers from subsystem topology."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from .model import RepositoryModel


@dataclass(frozen=True, slots=True)
class ArchitectureLayer:
    level: int
    zones: tuple[str, ...]
    role: str

    def as_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "zones": list(self.zones),
            "role": self.role,
        }


@dataclass(frozen=True, slots=True)
class ArchitectureLayers:
    layers: tuple[ArchitectureLayer, ...]
    cyclic_zones: tuple[str, ...]
    roots: tuple[str, ...]
    leaves: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "layers": [item.as_dict() for item in self.layers],
            "cyclic_zones": list(self.cyclic_zones),
            "roots": list(self.roots),
            "leaves": list(self.leaves),
        }


def derive_architecture_layers(model: RepositoryModel) -> ArchitectureLayers:
    zones = {item.name for item in model.subsystems}
    cyclic = {
        zone
        for cycle in model.cycles
        for zone in cycle
    }
    acyclic = zones - cyclic

    outbound: dict[str, set[str]] = defaultdict(set)
    inbound: dict[str, set[str]] = defaultdict(set)
    for edge in model.edges:
        if edge.source == edge.target:
            continue
        outbound[edge.source].add(edge.target)
        inbound[edge.target].add(edge.source)

    # Layers are dependency depth: leaves with no outbound dependencies are
    # level zero; their dependents rise one level at a time. Cyclic components
    # are excluded from the DAG and surfaced explicitly.
    unresolved = set(acyclic)
    level_by_zone: dict[str, int] = {}
    queue = deque(sorted(
        zone
        for zone in acyclic
        if not (outbound.get(zone, set()) & acyclic)
    ))
    for zone in queue:
        level_by_zone[zone] = 0

    while queue:
        dependency = queue.popleft()
        for dependent in sorted(inbound.get(dependency, ()) & acyclic):
            deps = outbound.get(dependent, set()) & acyclic
            if not deps.issubset(level_by_zone):
                continue
            level_by_zone[dependent] = 1 + max(
                (level_by_zone[item] for item in deps),
                default=-1,
            )
            queue.append(dependent)

    # Defensive fallback for malformed topology data that escaped cycle
    # detection: place unresolved nodes into an explicit final layer rather than
    # silently omitting them.
    unresolved -= set(level_by_zone)
    fallback_level = max(level_by_zone.values(), default=-1) + 1
    for zone in sorted(unresolved):
        level_by_zone[zone] = fallback_level

    grouped: dict[int, list[str]] = defaultdict(list)
    for zone, level in level_by_zone.items():
        grouped[level].append(zone)

    layers: list[ArchitectureLayer] = []
    max_level = max(grouped, default=0)
    for level in sorted(grouped):
        if level == 0:
            role = "foundation"
        elif level == max_level:
            role = "entry"
        else:
            role = "service"
        layers.append(ArchitectureLayer(
            level=level,
            zones=tuple(sorted(grouped[level])),
            role=role,
        ))

    roots = tuple(sorted(
        zone
        for zone in zones
        if not inbound.get(zone)
    ))
    leaves = tuple(sorted(
        zone
        for zone in zones
        if not outbound.get(zone)
    ))
    return ArchitectureLayers(
        layers=tuple(layers),
        cyclic_zones=tuple(sorted(cyclic)),
        roots=roots,
        leaves=leaves,
    )


def dependency_direction_violations(
    model: RepositoryModel,
) -> tuple[dict[str, object], ...]:
    architecture = derive_architecture_layers(model)
    level = {
        zone: layer.level
        for layer in architecture.layers
        for zone in layer.zones
    }
    findings: list[dict[str, object]] = []
    for edge in model.edges:
        if edge.source in architecture.cyclic_zones or edge.target in architecture.cyclic_zones:
            continue
        source_level = level.get(edge.source)
        target_level = level.get(edge.target)
        if source_level is None or target_level is None:
            continue
        # A higher-level subsystem depending on a lower-level subsystem is the
        # derived normal direction. A lower-level dependency on a higher-level
        # subsystem inverts the architecture.
        if source_level < target_level:
            findings.append({
                "source": edge.source,
                "target": edge.target,
                "source_level": source_level,
                "target_level": target_level,
                "evidence_count": edge.evidence_count,
                "code": "architecture.layer-inversion",
            })
    return tuple(sorted(
        findings,
        key=lambda item: (
            item["source_level"],
            item["source"],
            item["target"],
        ),
    ))

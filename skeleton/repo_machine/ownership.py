"""Ownership analysis for machine-governed repository zones."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .config import MachineConfig
from .model import FileRecord, RepositoryModel


@dataclass(frozen=True, slots=True)
class OwnershipGap:
    zone: str
    owner: str
    severity: str
    reason: str
    paths: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "zone": self.zone,
            "owner": self.owner,
            "severity": self.severity,
            "reason": self.reason,
            "paths": list(self.paths),
        }


@dataclass(frozen=True, slots=True)
class OwnershipReport:
    owners: tuple[str, ...]
    zones_by_owner: tuple[tuple[str, tuple[str, ...]], ...]
    unclassified_paths: tuple[str, ...]
    gaps: tuple[OwnershipGap, ...]
    coverage_ratio: float

    def as_dict(self) -> dict[str, object]:
        return {
            "owners": list(self.owners),
            "zones_by_owner": {
                owner: list(zones)
                for owner, zones in self.zones_by_owner
            },
            "unclassified_paths": list(self.unclassified_paths),
            "gaps": [gap.as_dict() for gap in self.gaps],
            "coverage_ratio": self.coverage_ratio,
        }


def analyze_ownership(
    model: RepositoryModel,
    config: MachineConfig,
    *,
    sample_limit: int = 50,
) -> OwnershipReport:
    if isinstance(sample_limit, bool) or not isinstance(sample_limit, int) or not 1 <= sample_limit <= 1000:
        raise ValueError("sample_limit must be in [1,1000]")

    owner_zones: dict[str, set[str]] = {}
    for rule in config.zones:
        owner_zones.setdefault(rule.owner, set()).add(rule.name)

    unclassified = tuple(
        item.path
        for item in model.files
        if item.zone == "unclassified"
    )
    gaps: list[OwnershipGap] = []
    if unclassified:
        gaps.append(OwnershipGap(
            zone="unclassified",
            owner=config.default_owner,
            severity="medium" if len(unclassified) > 50 else "low",
            reason="paths are governed only by the default owner",
            paths=unclassified[:sample_limit],
        ))

    records_by_zone: dict[str, list[FileRecord]] = {}
    for record in model.files:
        records_by_zone.setdefault(record.zone, []).append(record)

    rules = {rule.name: rule for rule in config.zones}
    for subsystem in model.subsystems:
        if subsystem.name == "unclassified":
            continue
        rule = rules.get(subsystem.name)
        if rule is None:
            gaps.append(OwnershipGap(
                zone=subsystem.name,
                owner=config.default_owner,
                severity="medium",
                reason="live subsystem has no explicit zone rule",
                paths=tuple(item.path for item in records_by_zone.get(subsystem.name, ())[:sample_limit]),
            ))
            continue
        if subsystem.file_count == 0:
            gaps.append(OwnershipGap(
                zone=subsystem.name,
                owner=rule.owner,
                severity="info",
                reason="declared machine zone currently has no files",
                paths=(),
            ))
        if subsystem.criticality == "critical" and subsystem.test_files == 0 and subsystem.code_files:
            gaps.append(OwnershipGap(
                zone=subsystem.name,
                owner=rule.owner,
                severity="high",
                reason="critical code-bearing zone has no classified local tests",
                paths=tuple(
                    item.path
                    for item in records_by_zone.get(subsystem.name, ())
                    if item.kind == "source"
                )[:sample_limit],
            ))

    classified = len(model.files) - model.unclassified_count
    coverage = classified / max(1, len(model.files))
    return OwnershipReport(
        owners=tuple(sorted(owner_zones)),
        zones_by_owner=tuple(
            (owner, tuple(sorted(zones)))
            for owner, zones in sorted(owner_zones.items())
        ),
        unclassified_paths=unclassified[:sample_limit],
        gaps=tuple(sorted(gaps, key=lambda item: (item.severity, item.zone, item.reason))),
        coverage_ratio=round(coverage, 6),
    )


def owner_for_paths(
    model: RepositoryModel,
    paths: Iterable[str],
) -> tuple[str, ...]:
    lookup = {item.path: item.owner for item in model.files}
    owners = {
        lookup[path]
        for path in paths
        if path in lookup
    }
    return tuple(sorted(owners))

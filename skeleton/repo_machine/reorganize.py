"""Deterministic repository reorganization proposals.

This module proposes changes only. It never moves, renames or deletes files.
The mutation authority remains with the normal Secretary -> Worker path.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from .governance import validate_governance
from .hotspots import structural_hotspots
from .model import RepositoryModel
from .config import MachineConfig


@dataclass(frozen=True, slots=True)
class ReorganizationProposal:
    identity: str
    priority: int
    category: str
    zone: str
    paths: tuple[str, ...]
    objective: str
    constraints: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "priority": self.priority,
            "category": self.category,
            "zone": self.zone,
            "paths": list(self.paths),
            "objective": self.objective,
            "constraints": list(self.constraints),
        }


def propose_reorganization(
    model: RepositoryModel,
    config: MachineConfig,
    *,
    limit: int = 48,
) -> tuple[ReorganizationProposal, ...]:
    proposals: list[ReorganizationProposal] = []
    by_zone: dict[str, list[str]] = {}
    for record in model.files:
        by_zone.setdefault(record.zone, []).append(record.path)

    unclassified = sorted(by_zone.get("unclassified", ()))
    if unclassified:
        roots: dict[str, list[str]] = {}
        for path in unclassified:
            parts = PurePosixPath(path).parts
            root = parts[0] if parts else "<root>"
            roots.setdefault(root, []).append(path)
        for root, paths in sorted(roots.items(), key=lambda item: (-len(item[1]), item[0])):
            proposals.append(ReorganizationProposal(
                identity=f"classify:{root}",
                priority=min(100, 60 + len(paths)),
                category="classification",
                zone="unclassified",
                paths=tuple(paths[:50]),
                objective=f"Assign the {root!r} surface to an explicit canonical machine zone.",
                constraints=(
                    "preserve public import paths unless compatibility shims are added",
                    "update tests and machine zone rules in the same change",
                    "do not bulk-move unrelated files only for cosmetic uniformity",
                ),
            ))

    for cycle in model.cycles:
        proposals.append(ReorganizationProposal(
            identity="cycle:" + ":".join(cycle),
            priority=95,
            category="dependency-boundary",
            zone=cycle[0],
            paths=(),
            objective=f"Break cross-zone dependency cycle: {' -> '.join(cycle)}.",
            constraints=(
                "introduce the smallest stable interface or inversion point",
                "preserve runtime behavior",
                "add boundary regression tests before deleting compatibility paths",
            ),
        ))

    for hotspot in structural_hotspots(model, limit=100):
        if hotspot.scope != "file" or hotspot.score < 45:
            continue
        proposals.append(ReorganizationProposal(
            identity=f"hotspot:{hotspot.path}",
            priority=min(90, 40 + hotspot.score // 2),
            category="module-decomposition",
            zone=hotspot.zone,
            paths=(hotspot.path,),
            objective="Decompose the structural hotspot along cohesive responsibilities.",
            constraints=(
                "keep external API behavior stable",
                "prefer extraction over rewrite",
                "move tests with the extracted responsibility",
            ),
        ))

    for violation in validate_governance(model, config):
        if violation.code != "governance.overlapping-prefix":
            continue
        proposals.append(ReorganizationProposal(
            identity=f"governance:{violation.subject}",
            priority=70,
            category="governance",
            zone="repository",
            paths=(),
            objective="Remove ambiguous overlapping machine zone ownership.",
            constraints=(
                "one path must resolve deterministically to one primary zone",
                "preserve explicit owner and criticality metadata",
            ),
        ))

    dedup: dict[str, ReorganizationProposal] = {}
    for proposal in proposals:
        existing = dedup.get(proposal.identity)
        if existing is None or proposal.priority > existing.priority:
            dedup[proposal.identity] = proposal
    ordered = sorted(
        dedup.values(),
        key=lambda item: (-item.priority, item.category, item.identity),
    )
    return tuple(ordered[:limit])

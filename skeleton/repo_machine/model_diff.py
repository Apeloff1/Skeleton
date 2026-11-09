"""Semantic diff between two machine repository models."""
from __future__ import annotations

from dataclasses import dataclass

from .model import RepositoryModel


@dataclass(frozen=True, slots=True)
class RepositoryModelDelta:
    added_files: tuple[str, ...]
    removed_files: tuple[str, ...]
    changed_files: tuple[str, ...]
    added_zones: tuple[str, ...]
    removed_zones: tuple[str, ...]
    added_edges: tuple[str, ...]
    removed_edges: tuple[str, ...]
    new_cycles: tuple[tuple[str, ...], ...]
    resolved_cycles: tuple[tuple[str, ...], ...]
    finding_delta: int
    unclassified_delta: int

    def as_dict(self) -> dict[str, object]:
        return {
            "added_files": list(self.added_files),
            "removed_files": list(self.removed_files),
            "changed_files": list(self.changed_files),
            "added_zones": list(self.added_zones),
            "removed_zones": list(self.removed_zones),
            "added_edges": list(self.added_edges),
            "removed_edges": list(self.removed_edges),
            "new_cycles": [list(item) for item in self.new_cycles],
            "resolved_cycles": [list(item) for item in self.resolved_cycles],
            "finding_delta": self.finding_delta,
            "unclassified_delta": self.unclassified_delta,
        }


def _edge_key(edge) -> str:
    return f"{edge.source}->{edge.target}:{edge.kind}"


def compare_models(
    before: RepositoryModel,
    after: RepositoryModel,
) -> RepositoryModelDelta:
    before_files = {item.path: item.sha256 for item in before.files}
    after_files = {item.path: item.sha256 for item in after.files}
    shared = set(before_files) & set(after_files)
    before_zones = {item.name for item in before.subsystems}
    after_zones = {item.name for item in after.subsystems}
    before_edges = {_edge_key(item) for item in before.edges}
    after_edges = {_edge_key(item) for item in after.edges}
    before_cycles = set(before.cycles)
    after_cycles = set(after.cycles)
    return RepositoryModelDelta(
        added_files=tuple(sorted(set(after_files) - set(before_files))),
        removed_files=tuple(sorted(set(before_files) - set(after_files))),
        changed_files=tuple(sorted(
            path for path in shared
            if before_files[path] != after_files[path]
        )),
        added_zones=tuple(sorted(after_zones - before_zones)),
        removed_zones=tuple(sorted(before_zones - after_zones)),
        added_edges=tuple(sorted(after_edges - before_edges)),
        removed_edges=tuple(sorted(before_edges - after_edges)),
        new_cycles=tuple(sorted(after_cycles - before_cycles)),
        resolved_cycles=tuple(sorted(before_cycles - after_cycles)),
        finding_delta=len(after.findings) - len(before.findings),
        unclassified_delta=after.unclassified_count - before.unclassified_count,
    )

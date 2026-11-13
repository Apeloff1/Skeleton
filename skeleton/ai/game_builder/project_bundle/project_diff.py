"""File-level diffs between saved versions, plus optional design-graph diff."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeleton.forge.creator.design_graph import parse_design_graph
from skeleton.forge.creator.semantic_diff import semantic_diff

from .manifest import BundleManifest
from .project_save import ProjectSaver

DESIGN_GRAPH_PATH = "game/design_graph.json"


@dataclass(frozen=True, slots=True)
class FileDiff:
    base_sequence: int
    target_sequence: int
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def payload(self) -> dict[str, Any]:
        return {"base": self.base_sequence, "target": self.target_sequence,
                "added": list(self.added), "removed": list(self.removed), "changed": list(self.changed)}


def diff_manifests(base: BundleManifest, target: BundleManifest) -> FileDiff:
    a, b = base.file_map(), target.file_map()
    return FileDiff(base.sequence, target.sequence,
                    tuple(sorted(set(b) - set(a))), tuple(sorted(set(a) - set(b))),
                    tuple(sorted(p for p in set(a) & set(b) if a[p] != b[p])))


def diff_sequences(saver: ProjectSaver, project_id: str, base: int, target: int, *,
                   design: bool = False) -> dict[str, Any]:
    """Diff two retained versions; with ``design=True`` also semantic-diff the design graph."""
    va = saver.load(project_id, sequence=base)
    vb = saver.load(project_id, sequence=target)
    out: dict[str, Any] = {"files": diff_manifests(va.manifest, vb.manifest).payload()}
    if design:
        ga, gb = va.files.get(DESIGN_GRAPH_PATH), vb.files.get(DESIGN_GRAPH_PATH)
        if ga is None or gb is None:
            out["design"] = None  # one side has no design graph to compare
        else:
            out["design"] = semantic_diff(parse_design_graph(ga), parse_design_graph(gb)).to_dict()
    return out


__all__ = ["DESIGN_GRAPH_PATH", "FileDiff", "diff_manifests", "diff_sequences"]

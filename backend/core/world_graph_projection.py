"""Read-only projections from canonical :class:`WorldGraph` state.

The cockpit needs authoritative revision/hash synchronization without acquiring a
new mutation path. These helpers deliberately expose only bounded metadata and
aggregate counts; callers must use the existing revision-gated patch machinery
for writes.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from core.world_graph import WorldGraph

_PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:/-]+$")
_MAX_PROJECT_ID_LENGTH = 256
_MAX_SOURCE_LENGTH = 128


@dataclass(frozen=True, slots=True)
class WorldGraphProjection:
    project_id: str | None
    revision: int
    semantic_hash: str
    dirty: bool
    source: str
    node_count: int
    edge_count: int
    writable: bool = False

    def cockpit_state(self) -> dict[str, object]:
        """Return the exact camelCase state understood by the preview bridge."""

        return {
            **({"projectId": self.project_id} if self.project_id is not None else {}),
            "revision": self.revision,
            "semanticHash": self.semantic_hash,
            "dirty": self.dirty,
            "source": self.source,
        }

    def as_dict(self) -> dict[str, object]:
        """Return diagnostics including counts and explicit read-only status."""

        return {
            **self.cockpit_state(),
            "nodeCount": self.node_count,
            "edgeCount": self.edge_count,
            "writable": self.writable,
        }


def _project_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > _MAX_PROJECT_ID_LENGTH
        or not _PROJECT_ID_PATTERN.fullmatch(normalized)
        or "://" in normalized
        or normalized.startswith(("/", "./", "../"))
        or any(
            segment in {"", ".", ".."}
            for segment in normalized.split("/")
        )
    ):
        raise ValueError("project_id must be a bounded canonical identifier")
    return normalized


def _source(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > _MAX_SOURCE_LENGTH:
        raise ValueError("source must be a non-empty bounded label")
    return normalized


def project_world_graph(
    graph: WorldGraph,
    *,
    project_id: str | None = None,
    dirty: bool = False,
    source: str = "world-graph",
) -> WorldGraphProjection:
    """Build a stable read-only metadata projection from one locked snapshot."""

    if not isinstance(graph, WorldGraph):
        raise TypeError("graph must be a WorldGraph")
    if not isinstance(dirty, bool):
        raise TypeError("dirty must be a boolean")

    snapshot = graph.snapshot()
    nodes = snapshot["nodes"]
    edges = snapshot["edges"]
    return WorldGraphProjection(
        project_id=_project_id(project_id),
        revision=snapshot["revision"],
        semantic_hash=snapshot["semantic_hash"],
        dirty=dirty,
        source=_source(source),
        node_count=len(nodes),
        edge_count=len(edges),
    )

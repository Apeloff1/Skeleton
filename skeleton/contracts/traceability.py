"""Canonical typed traceability graph for VOL-112.

The graph binds requirements, implementation, tests and evidence into one
deterministic, fail-closed lineage model. This module owns the contract;
`skeleton.automation.traceability` is a compatibility-only import surface.

Edges are intentionally explicit:

* IMPLEMENTS: implementation -> requirement
* VERIFIES: test -> implementation
* EVIDENCES: evidence -> test
* DEPENDS_ON: same-kind node -> same-kind node

The first three form typed provenance chains. `DEPENDS_ON` is restricted to
same-kind nodes and must remain acyclic so dependency direction is unambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import re
from itertools import islice
from typing import Iterable, Mapping

TRACEABILITY_SCHEMA = "skeleton.contracts.traceability.v1"
_MAX_NODES = 10_000
_MAX_EDGES = 50_000
_MAX_LOCATOR_LENGTH = 2_048
_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")


class TraceError(ValueError):
    """Traceability state is malformed, contradictory, or unsafe to consume."""


class NodeKind(str, Enum):
    REQUIREMENT = "requirement"
    IMPLEMENTATION = "implementation"
    TEST = "test"
    EVIDENCE = "evidence"


class EdgeKind(str, Enum):
    IMPLEMENTS = "implements"
    VERIFIES = "verifies"
    EVIDENCES = "evidences"
    DEPENDS_ON = "depends_on"


class TraversalDirection(str, Enum):
    """Direction relative to the stored source -> target edge."""

    FORWARD = "forward"
    REVERSE = "reverse"
    BOTH = "both"


class GapKind(str, Enum):
    REQUIREMENT_WITHOUT_IMPLEMENTATION = "requirement_without_implementation"
    IMPLEMENTATION_WITHOUT_REQUIREMENT = "implementation_without_requirement"
    IMPLEMENTATION_WITHOUT_TEST = "implementation_without_test"
    TEST_WITHOUT_IMPLEMENTATION = "test_without_implementation"
    TEST_WITHOUT_EVIDENCE = "test_without_evidence"
    EVIDENCE_WITHOUT_TEST = "evidence_without_test"


def _stable_id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise TraceError(f"{field} must be a stable identifier")
    return value


def _locator(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > _MAX_LOCATOR_LENGTH
    ):
        raise TraceError("node locator must be bounded canonical text")
    if any(ord(char) < 32 for char in value):
        raise TraceError("node locator contains control characters")
    return value


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TraceError("traceability state must be deterministic JSON") from exc
    return sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class TraceNode:
    node_id: str
    kind: NodeKind
    locator: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _stable_id(self.node_id, "node_id"))
        if not isinstance(self.kind, NodeKind):
            raise TraceError("kind must be NodeKind")
        object.__setattr__(self, "locator", _locator(self.locator))

    @property
    def digest(self) -> str:
        return _digest(
            [TRACEABILITY_SCHEMA, self.node_id, self.kind.value, self.locator]
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "node_id": self.node_id,
            "kind": self.kind.value,
            "locator": self.locator,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "TraceNode":
        if not isinstance(value, Mapping):
            raise TraceError("trace node payload must be a mapping")
        expected = {"node_id", "kind", "locator"}
        if set(value) != expected:
            raise TraceError("trace node payload has unknown or missing fields")
        try:
            kind = NodeKind(value["kind"])
        except (TypeError, ValueError) as exc:
            raise TraceError("unknown trace node kind") from exc
        return cls(
            node_id=value["node_id"],  # type: ignore[arg-type]
            kind=kind,
            locator=value["locator"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class TraceEdge:
    source_id: str
    target_id: str
    kind: EdgeKind

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_id", _stable_id(self.source_id, "source_id")
        )
        object.__setattr__(
            self, "target_id", _stable_id(self.target_id, "target_id")
        )
        if not isinstance(self.kind, EdgeKind):
            raise TraceError("kind must be EdgeKind")
        if self.source_id == self.target_id:
            raise TraceError("self trace edge")

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.source_id, self.target_id, self.kind.value)

    @property
    def digest(self) -> str:
        return _digest([TRACEABILITY_SCHEMA, *self.identity])

    def to_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "kind": self.kind.value,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "TraceEdge":
        if not isinstance(value, Mapping):
            raise TraceError("trace edge payload must be a mapping")
        expected = {"source_id", "target_id", "kind"}
        if set(value) != expected:
            raise TraceError("trace edge payload has unknown or missing fields")
        try:
            kind = EdgeKind(value["kind"])
        except (TypeError, ValueError) as exc:
            raise TraceError("unknown trace edge kind") from exc
        return cls(
            source_id=value["source_id"],  # type: ignore[arg-type]
            target_id=value["target_id"],  # type: ignore[arg-type]
            kind=kind,
        )


@dataclass(frozen=True, slots=True)
class TraceGap:
    kind: GapKind
    node_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, GapKind):
            raise TraceError("gap kind must be GapKind")
        object.__setattr__(self, "node_id", _stable_id(self.node_id, "node_id"))


@dataclass(frozen=True, slots=True)
class TraceabilityReport:
    matrix_digest: str
    gaps: tuple[TraceGap, ...]

    @property
    def complete(self) -> bool:
        return not self.gaps

    @property
    def digest(self) -> str:
        return _digest(
            [
                TRACEABILITY_SCHEMA,
                self.matrix_digest,
                [(gap.kind.value, gap.node_id) for gap in self.gaps],
                self.complete,
            ]
        )


class TraceabilityMatrix:
    """Immutable-by-construction typed graph with deterministic query results."""

    _TYPED_EDGE_SHAPES = {
        EdgeKind.IMPLEMENTS: (NodeKind.IMPLEMENTATION, NodeKind.REQUIREMENT),
        EdgeKind.VERIFIES: (NodeKind.TEST, NodeKind.IMPLEMENTATION),
        EdgeKind.EVIDENCES: (NodeKind.EVIDENCE, NodeKind.TEST),
    }

    def __init__(
        self,
        nodes: Iterable[TraceNode],
        edges: Iterable[TraceEdge],
    ) -> None:
        try:
            materialized_nodes = tuple(islice(iter(nodes), _MAX_NODES + 1))
        except TypeError as exc:
            raise TypeError("nodes must be iterable") from exc
        try:
            materialized_edges = tuple(islice(iter(edges), _MAX_EDGES + 1))
        except TypeError as exc:
            raise TypeError("edges must be iterable") from exc

        if len(materialized_nodes) > _MAX_NODES:
            raise TraceError("trace node count exceeds safety bound")
        if len(materialized_edges) > _MAX_EDGES:
            raise TraceError("trace edge count exceeds safety bound")
        if any(not isinstance(node, TraceNode) for node in materialized_nodes):
            raise TypeError("nodes must contain TraceNode")
        if any(not isinstance(edge, TraceEdge) for edge in materialized_edges):
            raise TypeError("edges must contain TraceEdge")

        node_ids = [node.node_id for node in materialized_nodes]
        if len(node_ids) != len(set(node_ids)):
            raise TraceError("duplicate trace node")

        edge_ids = [edge.identity for edge in materialized_edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise TraceError("duplicate trace edge")

        self.nodes = {
            node.node_id: node
            for node in sorted(materialized_nodes, key=lambda item: item.node_id)
        }
        self.edges = tuple(
            sorted(
                materialized_edges,
                key=lambda item: (item.source_id, item.target_id, item.kind.value),
            )
        )

        for edge in self.edges:
            if edge.source_id not in self.nodes or edge.target_id not in self.nodes:
                raise TraceError("dangling trace edge")
            self._validate_edge(edge)

        self._forward = {node_id: set() for node_id in self.nodes}
        self._reverse = {node_id: set() for node_id in self.nodes}
        for edge in self.edges:
            self._forward[edge.source_id].add(edge.target_id)
            self._reverse[edge.target_id].add(edge.source_id)

        self._reject_dependency_cycles()

    def _validate_edge(self, edge: TraceEdge) -> None:
        source = self.nodes[edge.source_id]
        target = self.nodes[edge.target_id]
        expected = self._TYPED_EDGE_SHAPES.get(edge.kind)
        if expected is not None and (source.kind, target.kind) != expected:
            raise TraceError("contradictory trace edge types")
        if edge.kind is EdgeKind.DEPENDS_ON and source.kind is not target.kind:
            raise TraceError("dependency trace edge must connect same-kind nodes")

    def _reject_dependency_cycles(self) -> None:
        adjacency = {node_id: set() for node_id in self.nodes}
        for edge in self.edges:
            if edge.kind is EdgeKind.DEPENDS_ON:
                adjacency[edge.source_id].add(edge.target_id)

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visited:
                return
            if node_id in visiting:
                raise TraceError("dependency cycle")
            visiting.add(node_id)
            for target_id in sorted(adjacency[node_id]):
                visit(target_id)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in sorted(self.nodes):
            visit(node_id)

    @property
    def digest(self) -> str:
        return _digest(
            [
                TRACEABILITY_SCHEMA,
                [node.digest for node in self.nodes.values()],
                [edge.digest for edge in self.edges],
            ]
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": TRACEABILITY_SCHEMA,
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges],
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "TraceabilityMatrix":
        if not isinstance(value, Mapping):
            raise TraceError("traceability payload must be a mapping")
        expected = {"schema", "nodes", "edges", "digest"}
        if set(value) != expected:
            raise TraceError("traceability payload has unknown or missing fields")
        if value["schema"] != TRACEABILITY_SCHEMA:
            raise TraceError("unsupported traceability schema")
        nodes_raw = value["nodes"]
        edges_raw = value["edges"]
        if not isinstance(nodes_raw, list) or not isinstance(edges_raw, list):
            raise TraceError("traceability nodes and edges must be lists")
        matrix = cls(
            (TraceNode.from_dict(item) for item in nodes_raw),
            (TraceEdge.from_dict(item) for item in edges_raw),
        )
        if value["digest"] != matrix.digest:
            raise TraceError("traceability digest mismatch")
        return matrix

    def node(self, node_id: str) -> TraceNode:
        node_id = _stable_id(node_id, "node_id")
        try:
            return self.nodes[node_id]
        except KeyError as exc:
            raise TraceError("unknown trace node") from exc

    def edges_from(
        self,
        node_id: str,
        *,
        kind: EdgeKind | None = None,
    ) -> tuple[TraceEdge, ...]:
        self.node(node_id)
        if kind is not None and not isinstance(kind, EdgeKind):
            raise TypeError("kind must be EdgeKind or None")
        return tuple(
            edge
            for edge in self.edges
            if edge.source_id == node_id and (kind is None or edge.kind is kind)
        )

    def edges_to(
        self,
        node_id: str,
        *,
        kind: EdgeKind | None = None,
    ) -> tuple[TraceEdge, ...]:
        self.node(node_id)
        if kind is not None and not isinstance(kind, EdgeKind):
            raise TypeError("kind must be EdgeKind or None")
        return tuple(
            edge
            for edge in self.edges
            if edge.target_id == node_id and (kind is None or edge.kind is kind)
        )

    def traverse(
        self,
        start_id: str,
        *,
        direction: TraversalDirection = TraversalDirection.BOTH,
        include_start: bool = True,
    ) -> tuple[str, ...]:
        start_id = self.node(start_id).node_id
        if not isinstance(direction, TraversalDirection):
            raise TypeError("direction must be TraversalDirection")
        if not isinstance(include_start, bool):
            raise TypeError("include_start must be boolean")

        seen = {start_id}
        todo = [start_id]
        while todo:
            current = todo.pop()
            neighbors: set[str] = set()
            if direction in (TraversalDirection.FORWARD, TraversalDirection.BOTH):
                neighbors.update(self._forward[current])
            if direction in (TraversalDirection.REVERSE, TraversalDirection.BOTH):
                neighbors.update(self._reverse[current])
            for neighbor in sorted(neighbors, reverse=True):
                if neighbor not in seen:
                    seen.add(neighbor)
                    todo.append(neighbor)

        if not include_start:
            seen.remove(start_id)
        return tuple(sorted(seen))

    def impact(self, start_id: str) -> tuple[str, ...]:
        """Return the connected blast radius in both lineage directions."""

        return self.traverse(start_id, direction=TraversalDirection.BOTH)

    def provenance(self, start_id: str) -> tuple[str, ...]:
        """Follow stored source -> target edges toward upstream provenance."""

        return self.traverse(start_id, direction=TraversalDirection.FORWARD)

    def dependents(self, start_id: str) -> tuple[str, ...]:
        """Follow reverse edges toward downstream implementation/evidence."""

        return self.traverse(start_id, direction=TraversalDirection.REVERSE)

    def _lineage_neighbors(self, node_id: str, *, reverse: bool) -> tuple[str, ...]:
        lineage = {EdgeKind.IMPLEMENTS, EdgeKind.VERIFIES, EdgeKind.EVIDENCES}
        return tuple(sorted(
            (edge.source_id if reverse else edge.target_id)
            for edge in self.edges
            if edge.kind in lineage
            and (edge.target_id if reverse else edge.source_id) == node_id
        ))

    def _lineage(self, start_id: str, *, reverse: bool) -> tuple[str, ...]:
        start_id = self.node(start_id).node_id
        seen = {start_id}
        todo = [start_id]
        while todo:
            current = todo.pop()
            for neighbor in reversed(self._lineage_neighbors(current, reverse=reverse)):
                if neighbor not in seen:
                    seen.add(neighbor)
                    todo.append(neighbor)
        return tuple(sorted(seen))

    def requirements_for(self, node_id: str) -> tuple[str, ...]:
        return tuple(
            item for item in self._lineage(node_id, reverse=False)
            if self.nodes[item].kind is NodeKind.REQUIREMENT
        )

    def evidence_for(self, node_id: str) -> tuple[str, ...]:
        return tuple(
            item for item in self._lineage(node_id, reverse=True)
            if self.nodes[item].kind is NodeKind.EVIDENCE
        )

    def gaps(self) -> tuple[TraceGap, ...]:
        gaps: list[TraceGap] = []
        for node in self.nodes.values():
            incoming = self.edges_to(node.node_id)
            outgoing = self.edges_from(node.node_id)
            incoming_kinds = {edge.kind for edge in incoming}
            outgoing_kinds = {edge.kind for edge in outgoing}

            if (
                node.kind is NodeKind.REQUIREMENT
                and EdgeKind.IMPLEMENTS not in incoming_kinds
            ):
                gaps.append(
                    TraceGap(
                        GapKind.REQUIREMENT_WITHOUT_IMPLEMENTATION,
                        node.node_id,
                    )
                )
            elif node.kind is NodeKind.IMPLEMENTATION:
                if EdgeKind.IMPLEMENTS not in outgoing_kinds:
                    gaps.append(
                        TraceGap(
                            GapKind.IMPLEMENTATION_WITHOUT_REQUIREMENT,
                            node.node_id,
                        )
                    )
                if EdgeKind.VERIFIES not in incoming_kinds:
                    gaps.append(
                        TraceGap(
                            GapKind.IMPLEMENTATION_WITHOUT_TEST,
                            node.node_id,
                        )
                    )
            elif node.kind is NodeKind.TEST:
                if EdgeKind.VERIFIES not in outgoing_kinds:
                    gaps.append(
                        TraceGap(
                            GapKind.TEST_WITHOUT_IMPLEMENTATION,
                            node.node_id,
                        )
                    )
                if EdgeKind.EVIDENCES not in incoming_kinds:
                    gaps.append(
                        TraceGap(
                            GapKind.TEST_WITHOUT_EVIDENCE,
                            node.node_id,
                        )
                    )
            elif (
                node.kind is NodeKind.EVIDENCE
                and EdgeKind.EVIDENCES not in outgoing_kinds
            ):
                gaps.append(
                    TraceGap(GapKind.EVIDENCE_WITHOUT_TEST, node.node_id)
                )

        return tuple(sorted(gaps, key=lambda gap: (gap.kind.value, gap.node_id)))

    def report(self) -> TraceabilityReport:
        return TraceabilityReport(matrix_digest=self.digest, gaps=self.gaps())

    def orphan_requirements(self) -> tuple[str, ...]:
        return tuple(
            gap.node_id
            for gap in self.gaps()
            if gap.kind is GapKind.REQUIREMENT_WITHOUT_IMPLEMENTATION
        )


__all__ = [
    "TRACEABILITY_SCHEMA",
    "EdgeKind",
    "GapKind",
    "NodeKind",
    "TraceEdge",
    "TraceError",
    "TraceGap",
    "TraceNode",
    "TraceabilityMatrix",
    "TraceabilityReport",
    "TraversalDirection",
]

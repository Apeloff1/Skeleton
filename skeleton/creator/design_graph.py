"""Persistent, queryable creator design graph (#807 B012).

The graph is a deterministic snapshot contract. It persists creator/design
state as canonical JSON with a content digest and exposes typed node/edge
queries without executing gameplay code or mutating an engine.

B011 DesignPlan values can be projected into this graph so mechanics,
world/content/interface nodes, assumptions, constraints, validation evidence,
and dependency relations survive process boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping

from skeleton.creator.intent_compiler import DesignPlan
from skeleton.kernel.errors import SkeletonError


DESIGN_GRAPH_SCHEMA = "creator.design_graph.v1"
DESIGN_GRAPH_VERSION = 1
MAX_NODES = 4096
MAX_EDGES = 16_384
MAX_ATTRIBUTES = 64
MAX_CANONICAL_BYTES = 4 * 1024 * 1024
MAX_TEXT = 4096
MAX_ID = 160

_ID_RE = re.compile(r"^[a-z][a-z0-9._:-]{0,159}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
NODE_KINDS = frozenset(
    {
        "assumption", "asset", "concept", "constraint", "content", "evidence",
        "interface", "mechanic", "narrative", "scene", "system", "validation",
        "world",
    }
)
EDGE_KINDS = frozenset(
    {
        "assumes", "constrained_by", "contains", "depends_on", "produces",
        "references", "validated_by", "validates",
    }
)


class DesignGraphError(SkeletonError):
    """Persistent design graph violates the deterministic contract."""

    code = "CRE.DESIGN_GRAPH"
    http_status = 400


@dataclass(frozen=True, slots=True)
class DesignGraphNode:
    node_id: str
    kind: str
    label: str
    attributes: tuple[tuple[str, object], ...] = ()

    def attribute_map(self) -> dict[str, object]:
        return dict(self.attributes)

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.node_id,
            "kind": self.kind,
            "label": self.label,
            "attributes": dict(self.attributes),
        }


@dataclass(frozen=True, slots=True)
class DesignGraphEdge:
    edge_id: str
    kind: str
    source: str
    target: str
    attributes: tuple[tuple[str, object], ...] = ()

    def attribute_map(self) -> dict[str, object]:
        return dict(self.attributes)

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.edge_id,
            "kind": self.kind,
            "source": self.source,
            "target": self.target,
            "attributes": dict(self.attributes),
        }


@dataclass(frozen=True, slots=True)
class DesignGraphSnapshot:
    project_id: str
    revision: int
    nodes: tuple[DesignGraphNode, ...]
    edges: tuple[DesignGraphEdge, ...]
    source_plan_digest: str | None = None
    schema: str = DESIGN_GRAPH_SCHEMA
    schema_version: int = DESIGN_GRAPH_VERSION

    @property
    def digest(self) -> str:
        return _digest(self.to_payload(include_digest=False))

    def to_payload(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "revision": self.revision,
            "source_plan_digest": self.source_plan_digest,
            "nodes": [node.to_payload() for node in self.nodes],
            "edges": [edge.to_payload() for edge in self.edges],
        }
        if include_digest:
            payload["digest"] = self.digest
        return payload

    def serialize(self) -> str:
        return _canonical_json(self.to_payload())

    def node_map(self) -> dict[str, DesignGraphNode]:
        return {node.node_id: node for node in self.nodes}

    def edge_map(self) -> dict[str, DesignGraphEdge]:
        return {edge.edge_id: edge for edge in self.edges}

    def nodes_of_kind(self, kind: str) -> tuple[DesignGraphNode, ...]:
        checked = _node_kind(kind)
        return tuple(node for node in self.nodes if node.kind == checked)

    def outgoing(
        self, node_id: str, *, kind: str | None = None
    ) -> tuple[DesignGraphEdge, ...]:
        checked_id = _identifier(node_id, field="node_id")
        _require_node(self, checked_id)
        checked_kind = None if kind is None else _edge_kind(kind)
        return tuple(
            edge
            for edge in self.edges
            if edge.source == checked_id
            and (checked_kind is None or edge.kind == checked_kind)
        )

    def incoming(
        self, node_id: str, *, kind: str | None = None
    ) -> tuple[DesignGraphEdge, ...]:
        checked_id = _identifier(node_id, field="node_id")
        _require_node(self, checked_id)
        checked_kind = None if kind is None else _edge_kind(kind)
        return tuple(
            edge
            for edge in self.edges
            if edge.target == checked_id
            and (checked_kind is None or edge.kind == checked_kind)
        )

    def neighbors(
        self, node_id: str, *, kind: str | None = None
    ) -> tuple[DesignGraphNode, ...]:
        node_map = self.node_map()
        adjacent = {
            edge.target for edge in self.outgoing(node_id, kind=kind)
        } | {
            edge.source for edge in self.incoming(node_id, kind=kind)
        }
        return tuple(node_map[item] for item in sorted(adjacent))


def build_design_graph(
    *,
    project_id: str,
    nodes: Iterable[DesignGraphNode | Mapping[str, Any]],
    edges: Iterable[DesignGraphEdge | Mapping[str, Any]],
    revision: int = 0,
    source_plan_digest: str | None = None,
) -> DesignGraphSnapshot:
    checked_project = _identifier(project_id, field="project_id")
    checked_revision = _bounded_int(
        revision, field="revision", minimum=0, maximum=(1 << 63) - 1
    )
    checked_source = (
        None
        if source_plan_digest is None
        else _sha256(source_plan_digest, field="source_plan_digest")
    )
    normalized_nodes = _normalize_nodes(nodes)
    normalized_edges = _normalize_edges(edges)
    node_ids = {node.node_id for node in normalized_nodes}
    for edge in normalized_edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            raise DesignGraphError(
                "edge references unknown node",
                context={
                    "edge_id": edge.edge_id,
                    "source": edge.source,
                    "target": edge.target,
                },
            )
        if edge.source == edge.target:
            raise DesignGraphError(
                "self edges are forbidden",
                context={"edge_id": edge.edge_id},
            )
    snapshot = DesignGraphSnapshot(
        project_id=checked_project,
        revision=checked_revision,
        nodes=normalized_nodes,
        edges=normalized_edges,
        source_plan_digest=checked_source,
    )
    if len(snapshot.serialize().encode("utf-8")) > MAX_CANONICAL_BYTES:
        raise DesignGraphError("design graph exceeds canonical byte bound")
    return snapshot


def design_graph_from_plan(plan: DesignPlan) -> DesignGraphSnapshot:
    """Persist a B011 plan as typed, queryable graph entities and edges."""

    if not isinstance(plan, DesignPlan):
        raise DesignGraphError("plan must be a DesignPlan")
    nodes: list[DesignGraphNode] = []
    edges: list[DesignGraphEdge] = []

    for node in plan.nodes:
        nodes.append(
            DesignGraphNode(
                node_id=node.node_id,
                kind=node.kind,
                label=node.title,
                attributes=_attributes(
                    {
                        "summary": node.summary,
                        "editable": node.editable,
                        "source_path": node.source_path,
                    }
                ),
            )
        )
        for dep in node.depends_on:
            edges.append(
                DesignGraphEdge(
                    edge_id=_edge_id("depends", node.node_id, dep),
                    kind="depends_on",
                    source=node.node_id,
                    target=dep,
                )
            )

    for assumption in plan.assumptions:
        graph_id = _prefixed("assumption", assumption.assumption_id)
        nodes.append(
            DesignGraphNode(
                node_id=graph_id,
                kind="assumption",
                label=assumption.statement,
                attributes=_attributes({"source_path": assumption.source_path}),
            )
        )

    for constraint in plan.constraints:
        graph_id = _prefixed("constraint", constraint.constraint_id)
        nodes.append(
            DesignGraphNode(
                node_id=graph_id,
                kind="constraint",
                label=f"{constraint.field} {constraint.op}",
                attributes=_attributes(
                    {
                        "field": constraint.field,
                        "op": constraint.op,
                        "value": constraint.value,
                        "source_path": constraint.source_path,
                    }
                ),
            )
        )

    for validation in plan.validations:
        graph_id = _prefixed("evidence", validation.validation_id)
        nodes.append(
            DesignGraphNode(
                node_id=graph_id,
                kind="evidence",
                label=validation.requirement,
                attributes=_attributes(
                    {
                        "validation_id": validation.validation_id,
                        "source_path": validation.source_path,
                    }
                ),
            )
        )
        for target in validation.applies_to:
            edges.append(
                DesignGraphEdge(
                    edge_id=_edge_id("validates", graph_id, target),
                    kind="validates",
                    source=graph_id,
                    target=target,
                )
            )

    for node in plan.nodes:
        for assumption_id in node.assumption_ids:
            target = _prefixed("assumption", assumption_id)
            edges.append(
                DesignGraphEdge(
                    edge_id=_edge_id("assumes", node.node_id, target),
                    kind="assumes",
                    source=node.node_id,
                    target=target,
                )
            )
        for constraint_id in node.constraint_ids:
            target = _prefixed("constraint", constraint_id)
            edges.append(
                DesignGraphEdge(
                    edge_id=_edge_id("constraint", node.node_id, target),
                    kind="constrained_by",
                    source=node.node_id,
                    target=target,
                )
            )
        for validation_id in node.validation_ids:
            target = _prefixed("evidence", validation_id)
            edges.append(
                DesignGraphEdge(
                    edge_id=_edge_id("validated", node.node_id, target),
                    kind="validated_by",
                    source=node.node_id,
                    target=target,
                )
            )

    return build_design_graph(
        project_id=plan.request_id,
        nodes=nodes,
        edges=edges,
        revision=plan.revision,
        source_plan_digest=plan.digest(),
    )


def parse_design_graph(raw: str | bytes | Mapping[str, Any]) -> DesignGraphSnapshot:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DesignGraphError("design graph must be UTF-8") from exc
    if isinstance(raw, str):
        try:
            payload = json.loads(raw, object_pairs_hook=_no_duplicate_object)
        except DesignGraphError:
            raise
        except json.JSONDecodeError as exc:
            raise DesignGraphError("design graph is not valid JSON") from exc
    elif isinstance(raw, Mapping):
        payload = dict(raw)
    else:
        raise DesignGraphError("design graph must be JSON text/bytes or mapping")

    expected = {
        "schema", "schema_version", "project_id", "revision",
        "source_plan_digest", "nodes", "edges", "digest",
    }
    _exact_keys(payload, expected, "design graph")
    if payload["schema"] != DESIGN_GRAPH_SCHEMA:
        raise DesignGraphError("unsupported design graph schema")
    if payload["schema_version"] != DESIGN_GRAPH_VERSION:
        raise DesignGraphError("unsupported design graph version")
    if not isinstance(payload["nodes"], list) or not isinstance(payload["edges"], list):
        raise DesignGraphError("design graph nodes/edges must be lists")

    snapshot = build_design_graph(
        project_id=payload["project_id"],
        revision=payload["revision"],
        source_plan_digest=payload["source_plan_digest"],
        nodes=payload["nodes"],
        edges=payload["edges"],
    )
    declared = _sha256(payload["digest"], field="digest")
    if declared != snapshot.digest:
        raise DesignGraphError("design graph digest mismatch")
    return snapshot


def _normalize_nodes(
    values: Iterable[DesignGraphNode | Mapping[str, Any]],
) -> tuple[DesignGraphNode, ...]:
    if isinstance(values, (str, bytes, bytearray, Mapping)):
        raise DesignGraphError("nodes must be an iterable of node records")
    rows: list[DesignGraphNode] = []
    seen: set[str] = set()
    for raw in values:
        if len(rows) >= MAX_NODES:
            raise DesignGraphError("node count exceeds configured bound")
        row = _coerce_node(raw)
        if row.node_id in seen:
            raise DesignGraphError(
                "duplicate design graph node", context={"node_id": row.node_id}
            )
        seen.add(row.node_id)
        rows.append(row)
    return tuple(sorted(rows, key=lambda row: row.node_id))


def _normalize_edges(
    values: Iterable[DesignGraphEdge | Mapping[str, Any]],
) -> tuple[DesignGraphEdge, ...]:
    if isinstance(values, (str, bytes, bytearray, Mapping)):
        raise DesignGraphError("edges must be an iterable of edge records")
    rows: list[DesignGraphEdge] = []
    seen: set[str] = set()
    for raw in values:
        if len(rows) >= MAX_EDGES:
            raise DesignGraphError("edge count exceeds configured bound")
        row = _coerce_edge(raw)
        if row.edge_id in seen:
            raise DesignGraphError(
                "duplicate design graph edge", context={"edge_id": row.edge_id}
            )
        seen.add(row.edge_id)
        rows.append(row)
    return tuple(
        sorted(rows, key=lambda row: (row.source, row.kind, row.target, row.edge_id))
    )


def _coerce_node(raw: DesignGraphNode | Mapping[str, Any]) -> DesignGraphNode:
    if isinstance(raw, DesignGraphNode):
        return DesignGraphNode(
            node_id=_identifier(raw.node_id, field="node_id"),
            kind=_node_kind(raw.kind),
            label=_text(raw.label, field="label"),
            attributes=_attribute_pairs(raw.attributes),
        )
    if not isinstance(raw, Mapping):
        raise DesignGraphError("node must be DesignGraphNode or mapping")
    _exact_keys(raw, {"id", "kind", "label", "attributes"}, "node")
    return DesignGraphNode(
        node_id=_identifier(raw["id"], field="node_id"),
        kind=_node_kind(raw["kind"]),
        label=_text(raw["label"], field="label"),
        attributes=_attributes(raw["attributes"]),
    )


def _coerce_edge(raw: DesignGraphEdge | Mapping[str, Any]) -> DesignGraphEdge:
    if isinstance(raw, DesignGraphEdge):
        return DesignGraphEdge(
            edge_id=_identifier(raw.edge_id, field="edge_id"),
            kind=_edge_kind(raw.kind),
            source=_identifier(raw.source, field="source"),
            target=_identifier(raw.target, field="target"),
            attributes=_attribute_pairs(raw.attributes),
        )
    if not isinstance(raw, Mapping):
        raise DesignGraphError("edge must be DesignGraphEdge or mapping")
    _exact_keys(raw, {"id", "kind", "source", "target", "attributes"}, "edge")
    return DesignGraphEdge(
        edge_id=_identifier(raw["id"], field="edge_id"),
        kind=_edge_kind(raw["kind"]),
        source=_identifier(raw["source"], field="source"),
        target=_identifier(raw["target"], field="target"),
        attributes=_attributes(raw["attributes"]),
    )


def _attribute_pairs(
    raw: Iterable[tuple[str, object]],
) -> tuple[tuple[str, object], ...]:
    rows: list[tuple[str, object]] = []
    seen: set[str] = set()
    for pair in raw:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise DesignGraphError("attribute pairs must contain key/value tuples")
        key, value = pair
        checked_key = _identifier(key, field="attribute key")
        if checked_key in seen:
            raise DesignGraphError(
                "duplicate attribute key",
                context={"key": checked_key},
            )
        seen.add(checked_key)
        if len(rows) >= MAX_ATTRIBUTES:
            raise DesignGraphError("attribute count exceeds configured bound")
        rows.append((checked_key, _scalar(value, field=f"attribute {checked_key}")))
    return tuple(sorted(rows))


def _attributes(raw: Any) -> tuple[tuple[str, object], ...]:
    if not isinstance(raw, Mapping):
        raise DesignGraphError("attributes must be a mapping")
    if len(raw) > MAX_ATTRIBUTES:
        raise DesignGraphError("attribute count exceeds configured bound")
    rows: list[tuple[str, object]] = []
    for key, value in raw.items():
        checked_key = _identifier(key, field="attribute key")
        rows.append((checked_key, _scalar(value, field=f"attribute {checked_key}")))
    return tuple(sorted(rows))


def _scalar(value: Any, *, field: str) -> object:
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str) and len(value) > MAX_TEXT:
            raise DesignGraphError(f"{field} exceeds text bound")
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DesignGraphError(f"{field} must be finite")
        return value
    raise DesignGraphError(f"{field} must be a JSON scalar")


def _identifier(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or len(value) > MAX_ID or _ID_RE.fullmatch(value) is None:
        raise DesignGraphError(f"{field} must be a canonical identifier")
    return value


def _text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DesignGraphError(f"{field} must be a non-empty string")
    text = value.strip()
    if len(text) > MAX_TEXT or any(ch in text for ch in ("\x00", "\r")):
        raise DesignGraphError(f"{field} exceeds text/safety bound")
    return text


def _node_kind(value: Any) -> str:
    if not isinstance(value, str) or value not in NODE_KINDS:
        raise DesignGraphError("unsupported design graph node kind", context={"kind": value})
    return value


def _edge_kind(value: Any) -> str:
    if not isinstance(value, str) or value not in EDGE_KINDS:
        raise DesignGraphError("unsupported design graph edge kind", context={"kind": value})
    return value


def _sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise DesignGraphError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _bounded_int(value: Any, *, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DesignGraphError(f"{field} must be an integer")
    if value < minimum or value > maximum:
        raise DesignGraphError(f"{field} is out of range")
    return value


def _exact_keys(raw: Mapping[str, Any], expected: set[str], kind: str) -> None:
    extra = sorted(str(key) for key in raw if key not in expected)
    missing = sorted(key for key in expected if key not in raw)
    if extra or missing:
        raise DesignGraphError(
            f"{kind} keys mismatch", context={"missing": missing, "extra": extra}
        )


def _require_node(snapshot: DesignGraphSnapshot, node_id: str) -> None:
    if node_id not in snapshot.node_map():
        raise DesignGraphError("unknown design graph node", context={"node_id": node_id})


def _prefixed(prefix: str, value: str) -> str:
    return _identifier(f"{prefix}:{value}", field="generated node id")


def _edge_id(prefix: str, source: str, target: str) -> str:
    raw = f"{prefix}:{source}:{target}"
    if len(raw) <= MAX_ID and _ID_RE.fullmatch(raw):
        return raw
    suffix = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return _identifier(f"{prefix}:{suffix}", field="generated edge id")


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DesignGraphError("value is not canonically serializable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DesignGraphError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


__all__ = [
    "DESIGN_GRAPH_SCHEMA",
    "DESIGN_GRAPH_VERSION",
    "EDGE_KINDS",
    "NODE_KINDS",
    "DesignGraphEdge",
    "DesignGraphError",
    "DesignGraphNode",
    "DesignGraphSnapshot",
    "build_design_graph",
    "design_graph_from_plan",
    "parse_design_graph",
]

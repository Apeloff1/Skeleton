"""Transactional canonical project/world graph for Galaxy Studio.

The graph is the shared source of truth for editor UI, authored code, procedural
systems and Jeeves.  Mutations are expressed as revision-bound patches and are
applied atomically against a detached working copy.  A successful patch returns
an inverse patch, semantic hashes and a structured diff so AI-generated changes
can be previewed, measured, accepted or rolled back without bespoke undo logic.

This module intentionally has no database, renderer or model dependency.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from core.canonical_json import canonical_json_clone, canonical_json_sha256


class WorldGraphError(ValueError):
    """Base class for invalid world graph state or patch operations."""


class RevisionConflict(WorldGraphError):
    """Raised when a patch was prepared against stale graph/object state."""


class PatchRejected(WorldGraphError):
    """Raised when a patch violates graph invariants."""


def _identifier(value: str, field_name: str) -> str:
    value = (value or "").strip()
    if not value:
        raise PatchRejected(f"{field_name} must be non-empty")
    if len(value) > 256:
        raise PatchRejected(f"{field_name} exceeds 256 characters")
    return value


def _json_mapping(value: Mapping[str, Any] | None, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise PatchRejected(f"{field_name} must be an object")
    cloned = canonical_json_clone(dict(value))
    if not isinstance(cloned, dict):  # defensive; canonical clone preserves dict
        raise PatchRejected(f"{field_name} must be an object")
    return cloned


@dataclass
class WorldNode:
    node_id: str
    kind: str
    name: str
    parent_id: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    components: dict[str, dict[str, Any]] = field(default_factory=dict)
    package_ref: str | None = None
    revision: int = 1

    def __post_init__(self) -> None:
        self.node_id = _identifier(self.node_id, "node_id")
        self.kind = _identifier(self.kind, "kind")
        self.name = _identifier(self.name, "name")
        self.parent_id = None if self.parent_id is None else _identifier(self.parent_id, "parent_id")
        if self.parent_id == self.node_id:
            raise PatchRejected("node cannot parent itself")
        self.properties = _json_mapping(self.properties, "properties")
        if not isinstance(self.components, Mapping):
            raise PatchRejected("components must be an object")
        normalized: dict[str, dict[str, Any]] = {}
        for component, value in self.components.items():
            key = _identifier(str(component), "component name")
            normalized[key] = _json_mapping(value, f"component {key}")
        self.components = normalized
        if self.package_ref is not None:
            self.package_ref = _identifier(self.package_ref, "package_ref")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise PatchRejected("node revision must be an integer >= 1")

    def clone(self) -> "WorldNode":
        return WorldNode.from_dict(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "name": self.name,
            "parent_id": self.parent_id,
            "properties": canonical_json_clone(self.properties),
            "components": canonical_json_clone(self.components),
            "package_ref": self.package_ref,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorldNode":
        return cls(
            node_id=value.get("node_id", ""),
            kind=value.get("kind", ""),
            name=value.get("name", ""),
            parent_id=value.get("parent_id"),
            properties=value.get("properties") or {},
            components=value.get("components") or {},
            package_ref=value.get("package_ref"),
            revision=value.get("revision", 1),
        )


@dataclass
class WorldEdge:
    edge_id: str
    source_id: str
    target_id: str
    kind: str
    properties: dict[str, Any] = field(default_factory=dict)
    revision: int = 1

    def __post_init__(self) -> None:
        self.edge_id = _identifier(self.edge_id, "edge_id")
        self.source_id = _identifier(self.source_id, "source_id")
        self.target_id = _identifier(self.target_id, "target_id")
        self.kind = _identifier(self.kind, "edge kind")
        self.properties = _json_mapping(self.properties, "edge properties")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise PatchRejected("edge revision must be an integer >= 1")

    def clone(self) -> "WorldEdge":
        return WorldEdge.from_dict(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "kind": self.kind,
            "properties": canonical_json_clone(self.properties),
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorldEdge":
        return cls(
            edge_id=value.get("edge_id", ""),
            source_id=value.get("source_id", ""),
            target_id=value.get("target_id", ""),
            kind=value.get("kind", ""),
            properties=value.get("properties") or {},
            revision=value.get("revision", 1),
        )


@dataclass(frozen=True)
class PatchOp:
    op: str
    target: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    expected_revision: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "op", _identifier(self.op, "op").lower())
        object.__setattr__(self, "target", _identifier(self.target, "target"))
        object.__setattr__(self, "payload", _json_mapping(self.payload, "patch payload"))
        if self.expected_revision is not None:
            if (
                isinstance(self.expected_revision, bool)
                or not isinstance(self.expected_revision, int)
                or self.expected_revision < 1
            ):
                raise PatchRejected("expected_revision must be an integer >= 1")

    def as_dict(self) -> dict[str, Any]:
        return {
            "op": self.op,
            "target": self.target,
            "payload": canonical_json_clone(dict(self.payload)),
            "expected_revision": self.expected_revision,
        }


@dataclass(frozen=True)
class WorldPatch:
    base_revision: int
    operations: Sequence[PatchOp]
    patch_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    author: str = "system"
    capability: str | None = None
    evidence_ids: Sequence[str] = field(default_factory=tuple)
    expected_semantic_hash: str | None = None
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if isinstance(self.base_revision, bool) or not isinstance(self.base_revision, int) or self.base_revision < 0:
            raise PatchRejected("base_revision must be an integer >= 0")
        object.__setattr__(self, "patch_id", _identifier(self.patch_id, "patch_id"))
        object.__setattr__(self, "author", _identifier(self.author, "author"))
        if self.capability is not None:
            object.__setattr__(self, "capability", _identifier(self.capability, "capability"))
        ops = tuple(op if isinstance(op, PatchOp) else PatchOp(**op) for op in self.operations)
        if not ops:
            raise PatchRejected("patch must contain at least one operation")
        object.__setattr__(self, "operations", ops)
        object.__setattr__(
            self,
            "evidence_ids",
            tuple(dict.fromkeys(str(x).strip() for x in self.evidence_ids if str(x).strip())),
        )
        if self.expected_semantic_hash is not None:
            expected = self.expected_semantic_hash.strip().lower()
            if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
                raise PatchRejected("expected_semantic_hash must be a sha256 hex digest")
            object.__setattr__(self, "expected_semantic_hash", expected)

    def as_dict(self) -> dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "base_revision": self.base_revision,
            "operations": [op.as_dict() for op in self.operations],
            "author": self.author,
            "capability": self.capability,
            "evidence_ids": list(self.evidence_ids),
            "expected_semantic_hash": self.expected_semantic_hash,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class PatchResult:
    patch_id: str
    from_revision: int
    to_revision: int
    before_hash: str
    after_hash: str
    inverse_patch: WorldPatch
    changes: tuple[dict[str, Any], ...]
    evidence_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "from_revision": self.from_revision,
            "to_revision": self.to_revision,
            "before_hash": self.before_hash,
            "after_hash": self.after_hash,
            "inverse_patch": self.inverse_patch.as_dict(),
            "changes": [canonical_json_clone(row) for row in self.changes],
            "evidence_ids": list(self.evidence_ids),
        }


class WorldGraph:
    """Canonical mutable graph with atomic, reversible transactions."""

    _NODE_OPS = frozenset(
        {
            "create_node",
            "delete_node",
            "move_node",
            "set_name",
            "set_property",
            "remove_property",
            "set_component",
            "remove_component",
            "set_package_ref",
        }
    )
    _EDGE_OPS = frozenset(
        {"create_edge", "delete_edge", "set_edge_property", "remove_edge_property"}
    )

    def __init__(
        self,
        *,
        nodes: Iterable[WorldNode | Mapping[str, Any]] = (),
        edges: Iterable[WorldEdge | Mapping[str, Any]] = (),
        revision: int = 0,
    ) -> None:
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise PatchRejected("graph revision must be an integer >= 0")
        self._lock = threading.RLock()
        self._revision = revision
        self._nodes: dict[str, WorldNode] = {}
        self._edges: dict[str, WorldEdge] = {}
        for raw in nodes:
            node = raw.clone() if isinstance(raw, WorldNode) else WorldNode.from_dict(raw)
            if node.node_id in self._nodes:
                raise PatchRejected(f"duplicate node: {node.node_id}")
            self._nodes[node.node_id] = node
        for raw in edges:
            edge = raw.clone() if isinstance(raw, WorldEdge) else WorldEdge.from_dict(raw)
            if edge.edge_id in self._edges:
                raise PatchRejected(f"duplicate edge: {edge.edge_id}")
            self._edges[edge.edge_id] = edge
        self._validate(self._nodes, self._edges)

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def get_node(self, node_id: str) -> WorldNode | None:
        with self._lock:
            node = self._nodes.get(node_id)
            return node.clone() if node else None

    def get_edge(self, edge_id: str) -> WorldEdge | None:
        with self._lock:
            edge = self._edges.get(edge_id)
            return edge.clone() if edge else None

    def children_of(self, node_id: str) -> tuple[WorldNode, ...]:
        with self._lock:
            rows = [node.clone() for node in self._nodes.values() if node.parent_id == node_id]
        rows.sort(key=lambda node: (node.name, node.node_id))
        return tuple(rows)

    def edges_for(self, node_id: str) -> tuple[WorldEdge, ...]:
        with self._lock:
            rows = [
                edge.clone()
                for edge in self._edges.values()
                if edge.source_id == node_id or edge.target_id == node_id
            ]
        rows.sort(key=lambda edge: edge.edge_id)
        return tuple(rows)

    @staticmethod
    def _semantic_payload(
        nodes: Mapping[str, WorldNode], edges: Mapping[str, WorldEdge]
    ) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "node_id": node.node_id,
                    "kind": node.kind,
                    "name": node.name,
                    "parent_id": node.parent_id,
                    "properties": node.properties,
                    "components": node.components,
                    "package_ref": node.package_ref,
                }
                for node in sorted(nodes.values(), key=lambda row: row.node_id)
            ],
            "edges": [
                {
                    "edge_id": edge.edge_id,
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "kind": edge.kind,
                    "properties": edge.properties,
                }
                for edge in sorted(edges.values(), key=lambda row: row.edge_id)
            ],
        }

    def semantic_hash(self) -> str:
        with self._lock:
            return canonical_json_sha256(self._semantic_payload(self._nodes, self._edges))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "revision": self._revision,
                "semantic_hash": canonical_json_sha256(
                    self._semantic_payload(self._nodes, self._edges)
                ),
                "nodes": [
                    node.as_dict()
                    for node in sorted(self._nodes.values(), key=lambda row: row.node_id)
                ],
                "edges": [
                    edge.as_dict()
                    for edge in sorted(self._edges.values(), key=lambda row: row.edge_id)
                ],
            }

    @classmethod
    def from_snapshot(cls, snapshot: Mapping[str, Any]) -> "WorldGraph":
        return cls(
            nodes=snapshot.get("nodes") or (),
            edges=snapshot.get("edges") or (),
            revision=snapshot.get("revision", 0),
        )

    @staticmethod
    def _validate(
        nodes: Mapping[str, WorldNode], edges: Mapping[str, WorldEdge]
    ) -> None:
        for node in nodes.values():
            if node.parent_id is not None and node.parent_id not in nodes:
                raise PatchRejected(
                    f"node {node.node_id} references missing parent {node.parent_id}"
                )

        # Parent chains must terminate.  Walk each chain independently so no
        # malformed subtree can hide behind an otherwise valid root.
        for start in nodes:
            seen: set[str] = set()
            cursor: str | None = start
            while cursor is not None:
                if cursor in seen:
                    raise PatchRejected(f"parent cycle detected at node {cursor}")
                seen.add(cursor)
                parent = nodes[cursor].parent_id
                cursor = parent

        for edge in edges.values():
            if edge.source_id not in nodes:
                raise PatchRejected(
                    f"edge {edge.edge_id} references missing source {edge.source_id}"
                )
            if edge.target_id not in nodes:
                raise PatchRejected(
                    f"edge {edge.edge_id} references missing target {edge.target_id}"
                )

    @staticmethod
    def _check_revision(actual: int, expected: int | None, target: str) -> None:
        if expected is not None and actual != expected:
            raise RevisionConflict(
                f"stale object revision for {target}: expected {expected}, got {actual}"
            )

    @staticmethod
    def _descendants(nodes: Mapping[str, WorldNode], node_id: str) -> set[str]:
        selected = {node_id}
        changed = True
        while changed:
            changed = False
            for candidate in nodes.values():
                if candidate.node_id not in selected and candidate.parent_id in selected:
                    selected.add(candidate.node_id)
                    changed = True
        return selected

    @staticmethod
    def _depth(nodes: Mapping[str, WorldNode], node_id: str) -> int:
        depth = 0
        cursor = nodes[node_id].parent_id
        while cursor is not None:
            depth += 1
            cursor = nodes[cursor].parent_id
        return depth

    def _apply_op(
        self,
        nodes: dict[str, WorldNode],
        edges: dict[str, WorldEdge],
        op: PatchOp,
    ) -> tuple[list[PatchOp], dict[str, Any]]:
        name = op.op
        payload = dict(op.payload)

        if name == "create_node":
            if op.target in nodes:
                raise PatchRejected(f"node already exists: {op.target}")
            node_payload = dict(payload)
            node_payload["node_id"] = op.target
            node = WorldNode.from_dict(node_payload)
            if node.parent_id is not None and node.parent_id not in nodes:
                raise PatchRejected(f"missing parent: {node.parent_id}")
            nodes[node.node_id] = node
            inverse = [PatchOp("delete_node", node.node_id, {"cascade": False, "delete_edges": False})]
            return inverse, {"op": name, "node_id": node.node_id, "kind": node.kind}

        if name == "delete_node":
            node = nodes.get(op.target)
            if node is None:
                raise PatchRejected(f"unknown node: {op.target}")
            self._check_revision(node.revision, op.expected_revision, op.target)
            cascade = bool(payload.get("cascade", False))
            selected = self._descendants(nodes, op.target) if cascade else {op.target}
            if not cascade:
                child = next((row.node_id for row in nodes.values() if row.parent_id == op.target), None)
                if child is not None:
                    raise PatchRejected(
                        f"node {op.target} has child {child}; use cascade=true"
                    )
            incident = [
                edge
                for edge in edges.values()
                if edge.source_id in selected or edge.target_id in selected
            ]
            if incident and not bool(payload.get("delete_edges", False)):
                raise PatchRejected(
                    f"node deletion touches {len(incident)} edge(s); set delete_edges=true"
                )

            deleted_nodes = sorted(
                (nodes[node_id].clone() for node_id in selected),
                key=lambda row: self._depth(nodes, row.node_id),
            )
            deleted_edges = [edge.clone() for edge in sorted(incident, key=lambda row: row.edge_id)]
            for edge in incident:
                edges.pop(edge.edge_id, None)
            for node_id in selected:
                nodes.pop(node_id, None)

            inverse: list[PatchOp] = []
            for deleted in deleted_nodes:
                node_payload = deleted.as_dict()
                node_payload.pop("node_id", None)
                inverse.append(PatchOp("create_node", deleted.node_id, node_payload))
            for deleted in deleted_edges:
                edge_payload = deleted.as_dict()
                edge_payload.pop("edge_id", None)
                inverse.append(PatchOp("create_edge", deleted.edge_id, edge_payload))
            return inverse, {
                "op": name,
                "node_id": op.target,
                "deleted_nodes": len(deleted_nodes),
                "deleted_edges": len(deleted_edges),
            }

        if name in {
            "move_node",
            "set_name",
            "set_property",
            "remove_property",
            "set_component",
            "remove_component",
            "set_package_ref",
        }:
            node = nodes.get(op.target)
            if node is None:
                raise PatchRejected(f"unknown node: {op.target}")
            self._check_revision(node.revision, op.expected_revision, op.target)

            if name == "move_node":
                old = node.parent_id
                new_parent = payload.get("parent_id")
                new_parent = None if new_parent is None else _identifier(str(new_parent), "parent_id")
                if new_parent is not None and new_parent not in nodes:
                    raise PatchRejected(f"missing parent: {new_parent}")
                node.parent_id = new_parent
                node.revision += 1
                return [PatchOp("move_node", op.target, {"parent_id": old})], {
                    "op": name,
                    "node_id": op.target,
                    "from_parent": old,
                    "to_parent": new_parent,
                }

            if name == "set_name":
                old = node.name
                node.name = _identifier(str(payload.get("name", "")), "name")
                node.revision += 1
                return [PatchOp("set_name", op.target, {"name": old})], {
                    "op": name,
                    "node_id": op.target,
                    "from": old,
                    "to": node.name,
                }

            if name in {"set_property", "remove_property"}:
                key = _identifier(str(payload.get("key", "")), "property key")
                existed = key in node.properties
                old = canonical_json_clone(node.properties[key]) if existed else None
                if name == "set_property":
                    if "value" not in payload:
                        raise PatchRejected("set_property requires value")
                    value = canonical_json_clone(payload["value"])
                    node.properties[key] = value
                    inverse = (
                        PatchOp("set_property", op.target, {"key": key, "value": old})
                        if existed
                        else PatchOp("remove_property", op.target, {"key": key})
                    )
                else:
                    if not existed:
                        raise PatchRejected(f"property does not exist: {key}")
                    node.properties.pop(key)
                    inverse = PatchOp("set_property", op.target, {"key": key, "value": old})
                node.revision += 1
                return [inverse], {"op": name, "node_id": op.target, "key": key}

            if name in {"set_component", "remove_component"}:
                key = _identifier(str(payload.get("component", "")), "component")
                existed = key in node.components
                old = canonical_json_clone(node.components[key]) if existed else None
                if name == "set_component":
                    value = _json_mapping(payload.get("value"), f"component {key}")
                    node.components[key] = value
                    inverse = (
                        PatchOp("set_component", op.target, {"component": key, "value": old})
                        if existed
                        else PatchOp("remove_component", op.target, {"component": key})
                    )
                else:
                    if not existed:
                        raise PatchRejected(f"component does not exist: {key}")
                    node.components.pop(key)
                    inverse = PatchOp("set_component", op.target, {"component": key, "value": old})
                node.revision += 1
                return [inverse], {"op": name, "node_id": op.target, "component": key}

            if name == "set_package_ref":
                old = node.package_ref
                raw = payload.get("package_ref")
                node.package_ref = None if raw is None else _identifier(str(raw), "package_ref")
                node.revision += 1
                return [PatchOp("set_package_ref", op.target, {"package_ref": old})], {
                    "op": name,
                    "node_id": op.target,
                    "from": old,
                    "to": node.package_ref,
                }

        if name == "create_edge":
            if op.target in edges:
                raise PatchRejected(f"edge already exists: {op.target}")
            edge_payload = dict(payload)
            edge_payload["edge_id"] = op.target
            edge = WorldEdge.from_dict(edge_payload)
            if edge.source_id not in nodes or edge.target_id not in nodes:
                raise PatchRejected("edge endpoints must exist")
            edges[edge.edge_id] = edge
            return [PatchOp("delete_edge", edge.edge_id)], {
                "op": name,
                "edge_id": edge.edge_id,
                "source_id": edge.source_id,
                "target_id": edge.target_id,
            }

        if name == "delete_edge":
            edge = edges.get(op.target)
            if edge is None:
                raise PatchRejected(f"unknown edge: {op.target}")
            self._check_revision(edge.revision, op.expected_revision, op.target)
            payload_before = edge.as_dict()
            payload_before.pop("edge_id", None)
            edges.pop(op.target)
            return [PatchOp("create_edge", op.target, payload_before)], {
                "op": name,
                "edge_id": op.target,
            }

        if name in {"set_edge_property", "remove_edge_property"}:
            edge = edges.get(op.target)
            if edge is None:
                raise PatchRejected(f"unknown edge: {op.target}")
            self._check_revision(edge.revision, op.expected_revision, op.target)
            key = _identifier(str(payload.get("key", "")), "edge property key")
            existed = key in edge.properties
            old = canonical_json_clone(edge.properties[key]) if existed else None
            if name == "set_edge_property":
                if "value" not in payload:
                    raise PatchRejected("set_edge_property requires value")
                edge.properties[key] = canonical_json_clone(payload["value"])
                inverse = (
                    PatchOp("set_edge_property", op.target, {"key": key, "value": old})
                    if existed
                    else PatchOp("remove_edge_property", op.target, {"key": key})
                )
            else:
                if not existed:
                    raise PatchRejected(f"edge property does not exist: {key}")
                edge.properties.pop(key)
                inverse = PatchOp("set_edge_property", op.target, {"key": key, "value": old})
            edge.revision += 1
            return [inverse], {"op": name, "edge_id": op.target, "key": key}

        raise PatchRejected(f"unsupported patch operation: {name}")

    def apply(self, patch: WorldPatch) -> PatchResult:
        if not isinstance(patch, WorldPatch):
            raise TypeError("patch must be a WorldPatch")
        with self._lock:
            if patch.base_revision != self._revision:
                raise RevisionConflict(
                    f"stale graph revision: patch={patch.base_revision}, current={self._revision}"
                )
            before_hash = canonical_json_sha256(
                self._semantic_payload(self._nodes, self._edges)
            )
            if (
                patch.expected_semantic_hash is not None
                and patch.expected_semantic_hash != before_hash
            ):
                raise RevisionConflict(
                    "semantic hash changed since patch planning"
                )

            # Detached copies make the transaction all-or-nothing.  No mutation
            # escapes to canonical state until every operation and global graph
            # invariant has passed.
            nodes = {key: value.clone() for key, value in self._nodes.items()}
            edges = {key: value.clone() for key, value in self._edges.items()}
            inverse_groups: list[list[PatchOp]] = []
            changes: list[dict[str, Any]] = []
            for op in patch.operations:
                inverse, change = self._apply_op(nodes, edges, op)
                inverse_groups.append(inverse)
                changes.append(change)

            self._validate(nodes, edges)
            after_hash = canonical_json_sha256(self._semantic_payload(nodes, edges))
            new_revision = self._revision + 1

            # Undo operations execute in reverse transaction order; each
            # operation's own inverse list is already ordered for restoration.
            inverse_ops: list[PatchOp] = []
            for group in reversed(inverse_groups):
                inverse_ops.extend(group)
            inverse_patch = WorldPatch(
                base_revision=new_revision,
                operations=tuple(inverse_ops),
                author=f"rollback:{patch.author}",
                capability="world.rollback",
                evidence_ids=patch.evidence_ids,
                expected_semantic_hash=after_hash,
            )

            self._nodes = nodes
            self._edges = edges
            old_revision = self._revision
            self._revision = new_revision
            return PatchResult(
                patch_id=patch.patch_id,
                from_revision=old_revision,
                to_revision=new_revision,
                before_hash=before_hash,
                after_hash=after_hash,
                inverse_patch=inverse_patch,
                changes=tuple(changes),
                evidence_ids=tuple(patch.evidence_ids),
            )

    def rollback(self, result: PatchResult) -> PatchResult:
        if not isinstance(result, PatchResult):
            raise TypeError("result must be a PatchResult")
        return self.apply(result.inverse_patch)

"""Content-addressed incremental build-graph primitive.

Smallest fail-closed planner for issue #940 / conflict domain
``build.incremental_graph``:

- nodes with declared dependency edges
- SHA-256 fingerprints that are stable for identical inputs
- invalidation of only the changed node and its dependents
- critical-path metadata
- bounded traversal and scale limits
- cycle detection that refuses to emit a graph

This module never executes a build command, never opens a network, and
never imports the repository-intelligence scanner. Trusted Git-index
snapshots (PR #862 / #935 / #973 contract) may be consumed as already-
serialized mappings or duck-typed objects with ``to_dict()`` / ``files``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence
import hashlib
import json

from skeleton.kernel.errors import SkeletonError


GRAPH_SCHEMA = 1
FINGERPRINT_ALGORITHM = "sha256"
MAX_NODES = 4096
MAX_EDGES = 16384
MAX_TRAVERSAL_VISITS = 65536
MAX_ID_LENGTH = 256
MAX_KIND_LENGTH = 64
MAX_INPUT_KEYS = 32
MAX_INPUT_VALUE_BYTES = 4096
MAX_COST = 1_000_000
SOURCE_KIND = "source"

_NODE_SPEC_KEYS = frozenset({"id", "node_id", "kind", "inputs", "dependencies", "cost"})
_TRACKED_FILE_KEYS = frozenset(
    {
        "path",
        "mode",
        "index_blob",
        "effective_blob",
        "size",
        "working_tree",
        "deleted",
        "working_mode",
    }
)
_REPO_INDEX_KEYS = frozenset(
    {
        "schema",
        "head",
        "object_format",
        "source_digest",
        "tracked_files",
        "tracked_bytes",
        "files",
    }
)


class IncrementalGraphError(SkeletonError):
    """Refuse to emit a build graph when the input cannot be trusted."""

    code = "BUILD.INCREMENTAL_GRAPH"
    http_status = 400


@dataclass(frozen=True, slots=True)
class NodeSpec:
    """Declared build unit. ``inputs`` are content payloads or digests."""

    node_id: str
    kind: str = "unit"
    inputs: Mapping[str, str] | None = None
    dependencies: Sequence[str] = ()
    cost: int = 1


@dataclass(frozen=True, slots=True)
class GraphNode:
    node_id: str
    kind: str
    inputs: tuple[tuple[str, str], ...]
    dependencies: tuple[str, ...]
    cost: int
    local_fingerprint: str
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.node_id,
            "kind": self.kind,
            "inputs": [[name, digest] for name, digest in self.inputs],
            "dependencies": list(self.dependencies),
            "cost": self.cost,
            "local_fingerprint": self.local_fingerprint,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class CriticalPath:
    nodes: tuple[str, ...]
    cost: int
    length: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": list(self.nodes),
            "cost": self.cost,
            "length": self.length,
        }


@dataclass(frozen=True, slots=True)
class IncrementalBuildGraph:
    """Immutable, content-addressed build graph."""

    schema: int
    algorithm: str
    fingerprint: str
    nodes: tuple[GraphNode, ...]
    topological_order: tuple[str, ...]
    critical_path: CriticalPath

    def node_map(self) -> dict[str, GraphNode]:
        return {node.node_id: node for node in self.nodes}

    def dependents(self) -> dict[str, tuple[str, ...]]:
        reverse: dict[str, list[str]] = {node.node_id: [] for node in self.nodes}
        for node in self.nodes:
            for dep in node.dependencies:
                reverse[dep].append(node.node_id)
        return {node_id: tuple(sorted(children)) for node_id, children in reverse.items()}

    def invalidate(self, changed: Iterable[str]) -> frozenset[str]:
        """Return ``changed`` plus every transitive dependent. Unknown ids fail closed."""
        known = self.node_map()
        seeds: list[str] = []
        seen_seed: set[str] = set()
        for raw in changed:
            node_id = _require_id(raw, field="changed")
            if node_id not in known:
                raise IncrementalGraphError(
                    "unknown changed node",
                    context={"node_id": node_id},
                )
            if node_id not in seen_seed:
                seen_seed.add(node_id)
                seeds.append(node_id)
        return _dependent_closure(self.dependents(), seeds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "algorithm": self.algorithm,
            "fingerprint": self.fingerprint,
            "nodes": [node.to_dict() for node in self.nodes],
            "topological_order": list(self.topological_order),
            "critical_path": self.critical_path.to_dict(),
        }

    def serialize(self) -> str:
        return _canonical_json(self.to_dict())


def build_incremental_graph(
    specs: Iterable[Any] = (),
    *,
    repo_index: Any | None = None,
    max_nodes: int = MAX_NODES,
    max_edges: int = MAX_EDGES,
    max_visits: int = MAX_TRAVERSAL_VISITS,
) -> IncrementalBuildGraph:
    """Build a deterministic graph or refuse.

    ``repo_index`` is optional trusted repository-intelligence output. The
    scanner is never imported or invoked from this function.
    """
    _require_positive_bound(max_nodes, "max_nodes")
    _require_positive_bound(max_edges, "max_edges")
    _require_positive_bound(max_visits, "max_visits")

    declared = [_coerce_spec(item) for item in _require_sequence(specs, field="specs")]
    sources = _source_specs_from_repo_index(repo_index) if repo_index is not None else []

    merged: dict[str, NodeSpec] = {}
    for spec in (*sources, *declared):
        if spec.node_id in merged:
            raise IncrementalGraphError(
                "duplicate node id",
                context={"node_id": spec.node_id},
            )
        merged[spec.node_id] = spec

    if not merged:
        raise IncrementalGraphError("graph requires at least one node")
    if len(merged) > max_nodes:
        raise IncrementalGraphError(
            "node count exceeds configured limit",
            context={"nodes": len(merged), "max_nodes": max_nodes},
        )

    edge_count = 0
    adjacency: dict[str, tuple[str, ...]] = {}
    for node_id, spec in merged.items():
        deps = spec.dependencies
        edge_count += len(deps)
        if edge_count > max_edges:
            raise IncrementalGraphError(
                "edge count exceeds configured limit",
                context={"edges": edge_count, "max_edges": max_edges},
            )
        missing = [dep for dep in deps if dep not in merged]
        if missing:
            raise IncrementalGraphError(
                "unknown dependency",
                context={"node_id": node_id, "dependency": missing[0]},
            )
        adjacency[node_id] = deps

    _detect_cycles(adjacency, max_visits=max_visits)
    order = _topological_order(adjacency, max_visits=max_visits)

    nodes_by_id: dict[str, GraphNode] = {}
    for node_id in order:
        spec = merged[node_id]
        input_pairs = _fingerprint_inputs(spec.inputs)
        local = _sha256(
            {
                "id": spec.node_id,
                "kind": spec.kind,
                "cost": spec.cost,
                "inputs": [[name, digest] for name, digest in input_pairs],
            }
        )
        dep_fingerprints = [[dep, nodes_by_id[dep].fingerprint] for dep in spec.dependencies]
        fingerprint = _sha256({"local": local, "dependencies": dep_fingerprints})
        nodes_by_id[node_id] = GraphNode(
            node_id=spec.node_id,
            kind=spec.kind,
            inputs=input_pairs,
            dependencies=spec.dependencies,
            cost=spec.cost,
            local_fingerprint=local,
            fingerprint=fingerprint,
        )

    ordered_nodes = tuple(nodes_by_id[node_id] for node_id in sorted(nodes_by_id))
    critical = _critical_path(ordered_nodes, order, max_visits=max_visits)
    graph_fingerprint = _sha256(
        {
            "schema": GRAPH_SCHEMA,
            "algorithm": FINGERPRINT_ALGORITHM,
            "nodes": [
                {
                    "id": node.node_id,
                    "fingerprint": node.fingerprint,
                    "dependencies": list(node.dependencies),
                }
                for node in ordered_nodes
            ],
        }
    )
    return IncrementalBuildGraph(
        schema=GRAPH_SCHEMA,
        algorithm=FINGERPRINT_ALGORITHM,
        fingerprint=graph_fingerprint,
        nodes=ordered_nodes,
        topological_order=order,
        critical_path=critical,
    )


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
        raise IncrementalGraphError("value is not canonically serializable") from exc


def _sha256(value: Any) -> str:
    encoded = _canonical_json(value).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_positive_bound(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise IncrementalGraphError(
            f"{field} must be a positive integer",
            context={"field": field},
        )


def _require_sequence(value: Any, *, field: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, bytearray, Mapping)):
        raise IncrementalGraphError(
            f"{field} must be a sequence",
            context={"field": field},
        )
    try:
        items = tuple(value)
    except TypeError as exc:
        raise IncrementalGraphError(
            f"{field} must be a sequence",
            context={"field": field},
        ) from exc
    return items


def _require_id(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise IncrementalGraphError(
            f"{field} must be a string",
            context={"field": field},
        )
    if not value or value != value.strip():
        raise IncrementalGraphError(
            f"{field} must be a non-empty trimmed string",
            context={"field": field},
        )
    if len(value) > MAX_ID_LENGTH:
        raise IncrementalGraphError(
            f"{field} exceeds max length",
            context={"field": field, "length": len(value)},
        )
    if "\x00" in value or "\\" in value or "\n" in value or "\r" in value:
        raise IncrementalGraphError(
            f"{field} contains unsafe characters",
            context={"field": field},
        )
    return value


def _require_kind(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise IncrementalGraphError("kind must be a non-empty trimmed string")
    if len(value) > MAX_KIND_LENGTH:
        raise IncrementalGraphError("kind exceeds max length", context={"length": len(value)})
    if any(ch in value for ch in ("\x00", "\n", "\r", "\\")):
        raise IncrementalGraphError("kind contains unsafe characters")
    return value


def _require_cost(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise IncrementalGraphError("cost must be an integer")
    if value < 1 or value > MAX_COST:
        raise IncrementalGraphError(
            "cost out of range",
            context={"cost": value, "max_cost": MAX_COST},
        )
    return value


def _unknown_keys(payload: Mapping[str, Any], allowed: frozenset[str], *, field: str) -> None:
    extra = sorted(key for key in payload if key not in allowed)
    if extra:
        raise IncrementalGraphError(
            f"malformed {field}: unknown keys",
            context={"field": field, "keys": extra},
        )


def _coerce_spec(raw: Any) -> NodeSpec:
    if isinstance(raw, NodeSpec):
        payload: dict[str, Any] = {
            "id": raw.node_id,
            "kind": raw.kind,
            "inputs": dict(raw.inputs or {}),
            "dependencies": list(raw.dependencies),
            "cost": raw.cost,
        }
    elif isinstance(raw, Mapping):
        payload = dict(raw)
    else:
        raise IncrementalGraphError(
            "node spec must be a mapping or NodeSpec",
            context={"type": type(raw).__name__},
        )
    _unknown_keys(payload, _NODE_SPEC_KEYS, field="node")
    node_id = payload.get("id", payload.get("node_id"))
    if node_id is None:
        raise IncrementalGraphError("node id is required")
    dependencies = _normalize_dependencies(payload.get("dependencies", ()))
    return NodeSpec(
        node_id=_require_id(node_id, field="id"),
        kind=_require_kind(payload.get("kind", "unit")),
        inputs=_normalize_inputs(payload.get("inputs", {})),
        dependencies=dependencies,
        cost=_require_cost(payload.get("cost", 1)),
    )


def _normalize_dependencies(raw: Any) -> tuple[str, ...]:
    items = _require_sequence(raw, field="dependencies")
    deps: list[str] = []
    seen: set[str] = set()
    for item in items:
        dep = _require_id(item, field="dependency")
        if dep in seen:
            raise IncrementalGraphError(
                "duplicate dependency",
                context={"dependency": dep},
            )
        seen.add(dep)
        deps.append(dep)
    return tuple(sorted(deps))


def _normalize_inputs(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping) or isinstance(raw, (str, bytes, bytearray)):
        raise IncrementalGraphError("inputs must be a mapping")
    if len(raw) > MAX_INPUT_KEYS:
        raise IncrementalGraphError(
            "input count exceeds configured limit",
            context={"inputs": len(raw), "max_input_keys": MAX_INPUT_KEYS},
        )
    normalized: dict[str, str] = {}
    for key, value in raw.items():
        name = _require_id(key, field="input")
        if not isinstance(value, str):
            raise IncrementalGraphError(
                "input values must be strings",
                context={"input": name},
            )
        encoded = value.encode("utf-8")
        if len(encoded) > MAX_INPUT_VALUE_BYTES:
            raise IncrementalGraphError(
                "input value exceeds max bytes",
                context={"input": name, "bytes": len(encoded)},
            )
        if "\x00" in value:
            raise IncrementalGraphError(
                "input value contains NUL",
                context={"input": name},
            )
        normalized[name] = value
    return normalized


def _fingerprint_inputs(inputs: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    pairs = []
    for name in sorted(inputs or ()):
        digest = hashlib.sha256((inputs or {})[name].encode("utf-8")).hexdigest()
        pairs.append((name, digest))
    return tuple(pairs)


def _coerce_repo_index(raw: Any) -> Mapping[str, Any]:
    if hasattr(raw, "to_dict") and callable(raw.to_dict):
        payload = raw.to_dict()
    elif isinstance(raw, Mapping):
        payload = dict(raw)
    else:
        files = getattr(raw, "files", None)
        if files is None:
            raise IncrementalGraphError(
                "repo index must be a mapping, snapshot, or object with files",
                context={"type": type(raw).__name__},
            )
        payload = {
            "schema": getattr(raw, "schema", GRAPH_SCHEMA),
            "head": getattr(raw, "head", None),
            "object_format": getattr(raw, "object_format", None),
            "source_digest": getattr(raw, "source_digest", None),
            "tracked_files": getattr(raw, "tracked_files", None),
            "tracked_bytes": getattr(raw, "tracked_bytes", None),
            "files": files,
        }
    if not isinstance(payload, Mapping):
        raise IncrementalGraphError("repo index payload must be a mapping")
    _unknown_keys(payload, _REPO_INDEX_KEYS, field="repo_index")
    return payload


def _source_specs_from_repo_index(raw: Any) -> list[NodeSpec]:
    payload = _coerce_repo_index(raw)
    files = payload.get("files")
    if not isinstance(files, Sequence) or isinstance(files, (str, bytes, bytearray)):
        raise IncrementalGraphError("repo index files must be a sequence")
    specs: list[NodeSpec] = []
    for item in files:
        spec = _source_spec_from_tracked_file(item)
        if spec is not None:
            specs.append(spec)
    return specs


def _source_spec_from_tracked_file(raw: Any) -> NodeSpec | None:
    if hasattr(raw, "__dataclass_fields__"):
        payload = {
            key: getattr(raw, key)
            for key in _TRACKED_FILE_KEYS
            if hasattr(raw, key)
        }
    elif isinstance(raw, Mapping):
        payload = dict(raw)
    else:
        raise IncrementalGraphError(
            "tracked file must be a mapping",
            context={"type": type(raw).__name__},
        )
    _unknown_keys(payload, _TRACKED_FILE_KEYS, field="tracked_file")
    if payload.get("deleted") is True:
        return None
    path = _require_id(payload.get("path"), field="path")
    blob = payload.get("effective_blob")
    if blob is None:
        blob = payload.get("index_blob")
    if not isinstance(blob, str) or not blob:
        raise IncrementalGraphError(
            "tracked file missing content digest",
            context={"path": path},
        )
    if "\x00" in blob:
        raise IncrementalGraphError("tracked file digest contains NUL", context={"path": path})
    mode = payload.get("mode", "100644")
    if not isinstance(mode, str) or not mode:
        raise IncrementalGraphError("tracked file mode must be a string", context={"path": path})
    size = payload.get("size", 0)
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise IncrementalGraphError("tracked file size must be a non-negative integer")
    return NodeSpec(
        node_id=path,
        kind=SOURCE_KIND,
        inputs={"blob": blob, "mode": mode, "size": str(size)},
        dependencies=(),
        cost=1,
    )


def _walk_bound(max_visits: int) -> Any:
    visits = {"count": 0}

    def bump() -> None:
        visits["count"] += 1
        if visits["count"] > max_visits:
            raise IncrementalGraphError(
                "traversal exceeded configured visit bound",
                context={"max_visits": max_visits},
            )

    return bump


def _detect_cycles(adjacency: Mapping[str, Sequence[str]], *, max_visits: int) -> None:
    bump = _walk_bound(max_visits)
    white = set(adjacency)
    gray: set[str] = set()
    black: set[str] = set()
    stack: list[str] = []

    def visit(node_id: str) -> None:
        bump()
        if node_id in black:
            return
        if node_id in gray:
            start = stack.index(node_id)
            cycle = stack[start:] + [node_id]
            raise IncrementalGraphError(
                "dependency cycle",
                context={"cycle": cycle},
            )
        gray.add(node_id)
        white.discard(node_id)
        stack.append(node_id)
        for dep in adjacency[node_id]:
            visit(dep)
        stack.pop()
        gray.discard(node_id)
        black.add(node_id)

    for node_id in sorted(white):
        if node_id in white:
            visit(node_id)


def _topological_order(
    adjacency: Mapping[str, Sequence[str]],
    *,
    max_visits: int,
) -> tuple[str, ...]:
    bump = _walk_bound(max_visits)
    indegree = {node_id: 0 for node_id in adjacency}
    dependents: dict[str, list[str]] = {node_id: [] for node_id in adjacency}
    for node_id, deps in adjacency.items():
        for dep in deps:
            bump()
            indegree[node_id] += 1
            dependents[dep].append(node_id)
    ready = deque(sorted(node_id for node_id, count in indegree.items() if count == 0))
    order: list[str] = []
    while ready:
        bump()
        node_id = ready.popleft()
        order.append(node_id)
        unlocked: list[str] = []
        for child in dependents[node_id]:
            bump()
            indegree[child] -= 1
            if indegree[child] == 0:
                unlocked.append(child)
        for child in sorted(unlocked):
            ready.append(child)
    if len(order) != len(adjacency):
        remaining = sorted(node_id for node_id in adjacency if node_id not in set(order))
        raise IncrementalGraphError(
            "dependency cycle",
            context={"cycle": remaining},
        )
    return tuple(order)


def _critical_path(
    nodes: Sequence[GraphNode],
    order: Sequence[str],
    *,
    max_visits: int,
) -> CriticalPath:
    bump = _walk_bound(max_visits)
    by_id = {node.node_id: node for node in nodes}
    dist: dict[str, int] = {}
    pred: dict[str, str | None] = {}
    for node_id in order:
        bump()
        node = by_id[node_id]
        best_dep: str | None = None
        best_cost = -1
        for dep in node.dependencies:
            bump()
            candidate = dist[dep]
            if (
                best_dep is None
                or candidate > best_cost
                or (candidate == best_cost and dep < best_dep)
            ):
                best_cost = candidate
                best_dep = dep
        dist[node_id] = node.cost if best_dep is None else best_cost + node.cost
        pred[node_id] = best_dep

    sink = min(dist, key=lambda node_id: (-dist[node_id], node_id))
    path: list[str] = []
    cursor: str | None = sink
    seen: set[str] = set()
    while cursor is not None:
        bump()
        if cursor in seen:
            raise IncrementalGraphError("dependency cycle", context={"cycle": [cursor]})
        seen.add(cursor)
        path.append(cursor)
        cursor = pred[cursor]
    path.reverse()
    return CriticalPath(nodes=tuple(path), cost=dist[sink], length=len(path))


def _dependent_closure(
    dependents: Mapping[str, Sequence[str]],
    seeds: Sequence[str],
) -> frozenset[str]:
    bump = _walk_bound(MAX_TRAVERSAL_VISITS)
    invalidated: set[str] = set()
    queue = deque(seeds)
    while queue:
        bump()
        node_id = queue.popleft()
        if node_id in invalidated:
            continue
        invalidated.add(node_id)
        for child in dependents[node_id]:
            if child not in invalidated:
                queue.append(child)
    return frozenset(invalidated)

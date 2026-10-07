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
import heapq
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

    def invalidate(
        self,
        changed: Iterable[str],
        *,
        max_visits: int = MAX_TRAVERSAL_VISITS,
    ) -> frozenset[str]:
        """Return ``changed`` plus every transitive dependent.

        Both seed ingestion and dependent traversal are bounded. Unknown ids
        fail closed.
        """
        _require_positive_bound(max_visits, "max_visits")
        known = self.node_map()
        seeds: list[str] = []
        seen_seed: set[str] = set()
        bump = _walk_bound(max_visits)
        for raw in changed:
            bump()
            node_id = _require_id(raw, field="changed")
            if node_id not in known:
                raise IncrementalGraphError(
                    "unknown changed node",
                    context={"node_id": node_id},
                )
            if node_id not in seen_seed:
                seen_seed.add(node_id)
                seeds.append(node_id)
        return _dependent_closure(self.dependents(), seeds, max_visits=max_visits)

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

    declared: list[NodeSpec] = []
    declared_edges = 0
    for item in _require_sequence(specs, field="specs", max_items=max_nodes):
        # Enforce the graph-wide edge budget while coercing each node so a
        # hostile input cannot materialize max_edges dependencies per node and
        # only fail after the full declared graph has been buffered.
        remaining_edges = max_edges - declared_edges
        spec = _coerce_spec(item, max_dependencies=remaining_edges)
        declared_edges += len(spec.dependencies)
        declared.append(spec)
    sources = (
        _source_specs_from_repo_index(repo_index, max_nodes=max_nodes)
        if repo_index is not None
        else []
    )

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


def _require_sequence(
    value: Any,
    *,
    field: str,
    max_items: int | None = None,
) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, bytearray, Mapping)):
        raise IncrementalGraphError(
            f"{field} must be a sequence",
            context={"field": field},
        )
    if max_items is not None and (
        isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 0
    ):
        raise IncrementalGraphError(
            "sequence bound must be a non-negative integer",
            context={"field": field},
        )
    items: list[Any] = []
    try:
        iterator = iter(value)
    except TypeError as exc:
        raise IncrementalGraphError(
            f"{field} must be a sequence",
            context={"field": field},
        ) from exc
    for item in iterator:
        if max_items is not None and len(items) >= max_items:
            raise IncrementalGraphError(
                f"{field} count exceeds configured limit",
                context={"field": field, "max_items": max_items},
            )
        items.append(item)
    return tuple(items)


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


def _coerce_spec(raw: Any, *, max_dependencies: int = MAX_EDGES) -> NodeSpec:
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
    if "id" in payload and "node_id" in payload:
        raise IncrementalGraphError("node spec cannot contain both id and node_id")
    node_id = payload.get("id", payload.get("node_id"))
    if node_id is None:
        raise IncrementalGraphError("node id is required")
    dependencies = _normalize_dependencies(
        payload.get("dependencies", ()),
        max_items=max_dependencies,
    )
    return NodeSpec(
        node_id=_require_id(node_id, field="id"),
        kind=_require_kind(payload.get("kind", "unit")),
        inputs=_normalize_inputs(payload.get("inputs", {})),
        dependencies=dependencies,
        cost=_require_cost(payload.get("cost", 1)),
    )


def _normalize_dependencies(raw: Any, *, max_items: int = MAX_EDGES) -> tuple[str, ...]:
    items = _require_sequence(raw, field="dependencies", max_items=max_items)
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
        required = tuple(sorted(_REPO_INDEX_KEYS))
        missing = [name for name in required if not hasattr(raw, name)]
        if missing:
            raise IncrementalGraphError(
                "repo index object is missing required fields",
                context={"fields": missing, "type": type(raw).__name__},
            )
        payload = {name: getattr(raw, name) for name in required}
    if not isinstance(payload, Mapping):
        raise IncrementalGraphError("repo index payload must be a mapping")
    _unknown_keys(payload, _REPO_INDEX_KEYS, field="repo_index")
    missing = sorted(_REPO_INDEX_KEYS.difference(payload))
    if missing:
        raise IncrementalGraphError(
            "repo index is missing required keys",
            context={"keys": missing},
        )
    return payload


_GIT_OBJECT_LENGTHS = {"sha1": 40, "sha256": 64}
_GIT_INDEX_MODES = frozenset({"100644", "100755", "120000", "160000"})
_HEX_DIGITS = frozenset("0123456789abcdef")


def _require_non_negative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise IncrementalGraphError(
            f"{field} must be a non-negative integer",
            context={"field": field},
        )
    return value


def _require_object_id(value: Any, *, field: str, object_format: str) -> str:
    expected = _GIT_OBJECT_LENGTHS[object_format]
    if (
        not isinstance(value, str)
        or len(value) != expected
        or any(ch not in _HEX_DIGITS for ch in value)
    ):
        raise IncrementalGraphError(
            f"{field} does not match {object_format} object id",
            context={"field": field, "object_format": object_format},
        )
    return value


def _require_git_mode(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or value not in _GIT_INDEX_MODES:
        raise IncrementalGraphError(
            f"{field} is not a supported git mode",
            context={"field": field},
        )
    return value


def _require_repo_path(value: Any) -> str:
    path = _require_id(value, field="path")
    parts = path.split("/")
    if path.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise IncrementalGraphError(
            "tracked file path is not canonical",
            context={"path": path},
        )
    return path


def _coerce_tracked_file(raw: Any, *, object_format: str) -> dict[str, Any]:
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
    missing = sorted(_TRACKED_FILE_KEYS.difference(payload))
    if missing:
        raise IncrementalGraphError(
            "tracked file is missing required keys",
            context={"keys": missing},
        )

    path = _require_repo_path(payload.get("path"))
    mode = _require_git_mode(payload.get("mode"), field="tracked file mode")
    index_blob = _require_object_id(
        payload.get("index_blob"),
        field="tracked file index_blob",
        object_format=object_format,
    )

    deleted = payload.get("deleted", False)
    working_tree = payload.get("working_tree", False)
    if not isinstance(deleted, bool):
        raise IncrementalGraphError("tracked file deleted must be a boolean")
    if not isinstance(working_tree, bool):
        raise IncrementalGraphError("tracked file working_tree must be a boolean")

    working_mode = payload.get("working_mode")
    if working_mode is not None:
        working_mode = _require_git_mode(working_mode, field="tracked file working_mode")

    effective_blob = payload.get("effective_blob", index_blob)
    if deleted:
        if effective_blob != "DELETED":
            raise IncrementalGraphError(
                "deleted tracked file must use DELETED effective_blob",
                context={"path": path},
            )
        if working_mode is not None:
            raise IncrementalGraphError(
                "deleted tracked file cannot carry a working_mode",
                context={"path": path},
            )
    else:
        effective_blob = _require_object_id(
            effective_blob,
            field="tracked file effective_blob",
            object_format=object_format,
        )

    size = _require_non_negative_int(payload.get("size"), field="tracked file size")
    if deleted and size != 0:
        raise IncrementalGraphError(
            "deleted tracked file size must be zero",
            context={"path": path, "size": size},
        )

    changed = deleted or effective_blob != index_blob or (
        working_mode is not None and working_mode != mode
    )
    if working_tree != changed:
        raise IncrementalGraphError(
            "tracked file working_tree flag contradicts content or mode state",
            context={"path": path},
        )
    if working_mode == mode:
        raise IncrementalGraphError(
            "tracked file working_mode must describe an actual mode change",
            context={"path": path},
        )

    return {
        "path": path,
        "mode": mode,
        "index_blob": index_blob,
        "effective_blob": effective_blob,
        "size": size,
        "working_tree": working_tree,
        "deleted": deleted,
        "working_mode": working_mode,
    }


def _repo_index_source_digest(files: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in files:
        effective_mode = item["working_mode"] or item["mode"]
        digest.update(item["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(item["mode"].encode("ascii"))
        digest.update(b"\0")
        digest.update(effective_mode.encode("ascii"))
        digest.update(b"\0")
        digest.update(item["index_blob"].encode("ascii"))
        digest.update(b"\0")
        digest.update(item["effective_blob"].encode("ascii"))
        digest.update(b"\0")
        digest.update(str(item["size"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(b"1" if item["working_tree"] else b"0")
        digest.update(b"1" if item["deleted"] else b"0")
        digest.update(b"\n")
    return digest.hexdigest()


def _validated_repo_index(raw: Any, *, max_nodes: int) -> tuple[dict[str, Any], ...]:
    payload = _coerce_repo_index(raw)
    schema = payload.get("schema")
    if isinstance(schema, bool) or schema != GRAPH_SCHEMA:
        raise IncrementalGraphError(
            "repo index schema is incompatible",
            context={"schema": schema, "expected": GRAPH_SCHEMA},
        )

    object_format = payload.get("object_format")
    if object_format not in _GIT_OBJECT_LENGTHS:
        raise IncrementalGraphError(
            "repo index object_format must be sha1 or sha256",
            context={"object_format": object_format},
        )

    head = payload.get("head")
    if head is not None:
        _require_object_id(head, field="repo index head", object_format=object_format)

    source_digest = payload.get("source_digest")
    if (
        not isinstance(source_digest, str)
        or len(source_digest) != 64
        or any(ch not in _HEX_DIGITS for ch in source_digest)
    ):
        raise IncrementalGraphError("repo index source_digest must be a sha256 digest")

    files = payload.get("files")
    if not isinstance(files, Sequence) or isinstance(files, (str, bytes, bytearray)):
        raise IncrementalGraphError("repo index files must be a sequence")
    if len(files) > max_nodes:
        raise IncrementalGraphError(
            "repo index file count exceeds configured node limit",
            context={"files": len(files), "max_nodes": max_nodes},
        )

    normalized = tuple(
        _coerce_tracked_file(item, object_format=object_format)
        for item in files
    )
    canonical_paths = sorted(
        (item["path"] for item in normalized),
        key=lambda path: path.encode("utf-8"),
    )
    actual_paths = [item["path"] for item in normalized]
    if actual_paths != canonical_paths:
        raise IncrementalGraphError("repo index files are not in canonical path order")
    if len(set(actual_paths)) != len(actual_paths):
        raise IncrementalGraphError("repo index contains duplicate tracked paths")

    tracked_files = _require_non_negative_int(
        payload.get("tracked_files"),
        field="repo index tracked_files",
    )
    if tracked_files != len(normalized):
        raise IncrementalGraphError(
            "repo index tracked_files mismatch",
            context={"declared": tracked_files, "actual": len(normalized)},
        )

    tracked_bytes = _require_non_negative_int(
        payload.get("tracked_bytes"),
        field="repo index tracked_bytes",
    )
    actual_bytes = sum(item["size"] for item in normalized)
    if tracked_bytes != actual_bytes:
        raise IncrementalGraphError(
            "repo index tracked_bytes mismatch",
            context={"declared": tracked_bytes, "actual": actual_bytes},
        )

    actual_digest = _repo_index_source_digest(normalized)
    if source_digest != actual_digest:
        raise IncrementalGraphError(
            "repo index source_digest mismatch",
            context={"declared": source_digest, "actual": actual_digest},
        )
    return normalized


def _source_specs_from_repo_index(raw: Any, *, max_nodes: int) -> list[NodeSpec]:
    specs: list[NodeSpec] = []
    for item in _validated_repo_index(raw, max_nodes=max_nodes):
        spec = _source_spec_from_tracked_file(item)
        if spec is not None:
            specs.append(spec)
    return specs


def _source_spec_from_tracked_file(payload: Mapping[str, Any]) -> NodeSpec | None:
    if payload["deleted"]:
        return None
    effective_mode = payload["working_mode"] or payload["mode"]
    return NodeSpec(
        node_id=payload["path"],
        kind=SOURCE_KIND,
        inputs={
            "blob": payload["effective_blob"],
            "mode": effective_mode,
            "size": str(payload["size"]),
        },
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
    state = {node_id: 0 for node_id in adjacency}
    path: list[str] = []
    path_index: dict[str, int] = {}

    for root in sorted(adjacency):
        if state[root] != 0:
            continue
        frames: list[tuple[str, int]] = [(root, 0)]
        while frames:
            node_id, next_index = frames[-1]
            if state[node_id] == 0:
                bump()
                state[node_id] = 1
                path_index[node_id] = len(path)
                path.append(node_id)

            deps = adjacency[node_id]
            if next_index >= len(deps):
                frames.pop()
                state[node_id] = 2
                path_index.pop(node_id, None)
                if path and path[-1] == node_id:
                    path.pop()
                continue

            dep = deps[next_index]
            frames[-1] = (node_id, next_index + 1)
            bump()
            if state[dep] == 0:
                frames.append((dep, 0))
                continue
            if state[dep] == 1:
                start = path_index[dep]
                raise IncrementalGraphError(
                    "dependency cycle",
                    context={"cycle": path[start:] + [dep]},
                )


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
    ready = [node_id for node_id, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        bump()
        node_id = heapq.heappop(ready)
        order.append(node_id)
        for child in sorted(dependents[node_id]):
            bump()
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    if len(order) != len(adjacency):
        emitted = set(order)
        remaining = sorted(node_id for node_id in adjacency if node_id not in emitted)
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
    *,
    max_visits: int = MAX_TRAVERSAL_VISITS,
) -> frozenset[str]:
    bump = _walk_bound(max_visits)
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

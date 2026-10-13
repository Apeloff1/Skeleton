"""Deterministic, bounded, typed capability graphs for local games/simulations.

Graph execution is read-only, has no dynamic imports, Python eval, shell,
network or filesystem operations. Data dependencies MUST refer to preceding
nodes. Each node invokes the admitted guarded operations and produces a
replayable hashed receipt. This is verified computation, not model inference.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .deterministic_capabilities import (
    CapabilityTaskError, OPERATIONS, execute_capability_task,
)

SCHEMA = "skeleton.offline_capability_graph.v1"
MAX_GRAPH_NODES = 32
MAX_GRAPH_BYTES = 65536
MAX_GRAPH_OUTPUT_BYTES = 65536
MAX_RESOLVE_DEPTH = 12
_ID = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")


class CapabilityGraphError(CapabilityTaskError):
    """The graph was ambiguous, unsafe, cyclic or over its computation budget."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    except (ValueError, TypeError, RecursionError) as exc:
        raise CapabilityGraphError("graph contains noncanonical JSON values") from exc


def _read_json(raw: bytes) -> dict[str, Any]:
    if not isinstance(raw, bytes) or len(raw) > MAX_GRAPH_BYTES:
        raise CapabilityGraphError("graph JSON must be bounded bytes")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise CapabilityGraphError("duplicate graph JSON key")
            result[key] = value
        return result
    try:
        parsed = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=unique,
            parse_constant=lambda _n: (_ for _ in ()).throw(
                CapabilityGraphError("nonfinite graph numeric constant")
            ),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise CapabilityGraphError("invalid graph JSON encoding") from exc
    if not isinstance(parsed, dict):
        raise CapabilityGraphError("graph JSON must be an object")
    return parsed


def _result_path(value: Any, path: list[Any]) -> Any:
    if not isinstance(path, list) or len(path) > 12:
        raise CapabilityGraphError("reference path must be a small list")
    current = value
    for part in path:
        if isinstance(current, dict):
            if not isinstance(part, str) or len(part) > 64 or part not in current:
                raise CapabilityGraphError("reference selects absent object field")
            current = current[part]
        elif isinstance(current, list):
            if type(part) is not int or not 0 <= part < len(current):
                raise CapabilityGraphError("reference selects missing array index")
            current = current[part]
        else:
            raise CapabilityGraphError("reference traverses a scalar value")
    return current


def _resolve(value: Any, completed: Mapping[str, Any], depth: int = 0) -> Any:
    if depth > MAX_RESOLVE_DEPTH:
        raise CapabilityGraphError("graph input nesting is excessive")
    if isinstance(value, dict):
        if "$ref" in value:
            if (
                set(value) not in ({"$ref"}, {"$ref", "path"})
                or not isinstance(value["$ref"], str)
                or value["$ref"] not in completed
            ):
                raise CapabilityGraphError("graph reference is forward, absent or invalid")
            path = value.get("path", [])
            return _result_path(completed[value["$ref"]], path)
        return {key: _resolve(item, completed, depth + 1)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item, completed, depth + 1) for item in value]
    return value


def execute_capability_graph(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Execute a bounded, strictly forward-only dataflow of verified tools."""
    if not isinstance(graph, dict) or set(graph) != {"schema_version", "nodes", "outputs"}:
        raise CapabilityGraphError("graph requires version, nodes and outputs only")
    if graph["schema_version"] != SCHEMA:
        raise CapabilityGraphError("unsupported capability graph schema")
    raw = _canonical(graph)
    if len(raw) > MAX_GRAPH_BYTES:
        raise CapabilityGraphError("graph is larger than admitted byte budget")
    nodes, requested = graph["nodes"], graph["outputs"]
    if (
        not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_GRAPH_NODES
        or not isinstance(requested, list) or not 1 <= len(requested) <= MAX_GRAPH_NODES
    ):
        raise CapabilityGraphError("graph node/output count exceeds budget")
    completed: dict[str, Any] = {}
    receipts: list[dict[str, Any]] = []
    total_resolved = 0
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or set(node) != {"id", "operation", "args"}:
            raise CapabilityGraphError("graph node has an invalid schema")
        node_id, operation = node["id"], node["operation"]
        if (
            not isinstance(node_id, str) or _ID.fullmatch(node_id) is None
            or node_id in completed
            or not isinstance(operation, str) or operation not in OPERATIONS
            or not isinstance(node["args"], dict)
        ):
            raise CapabilityGraphError("graph node identity/operation is invalid")
        args = _resolve(node["args"], completed)
        resolved_bytes = _canonical({"operation": operation, "args": args})
        total_resolved += len(resolved_bytes)
        if total_resolved > MAX_GRAPH_BYTES:
            raise CapabilityGraphError("graph intermediate input exceeds cumulative budget")
        try:
            result = execute_capability_task({"operation": operation, "args": args})
        except CapabilityTaskError as exc:
            raise CapabilityGraphError(
                f"graph node {index} ({node_id}) rejected by typed capability"
            ) from exc
        completed[node_id] = result["result"]
        receipts.append({
            "node": node_id,
            "operation": operation,
            "result_sha256": result["result_sha256"],
        })
    if (
        any(not isinstance(k, str) or k not in completed for k in requested)
        or len(set(requested)) != len(requested)
    ):
        raise CapabilityGraphError("graph outputs must be distinct completed node ids")
    result = {
        "schema_version": SCHEMA,
        "graph_sha256": hashlib.sha256(raw).hexdigest(),
        "node_count": len(receipts),
        "node_receipts": receipts,
        "outputs": {key: completed[key] for key in requested},
        "deterministic": True,
        "model_inference_used": False,
        "training_examples_added": 0,
        "network_access_used": False,
        "filesystem_access_used": False,
        "executor_authority_granted": False,
    }
    if len(_canonical(result)) > MAX_GRAPH_OUTPUT_BYTES:
        raise CapabilityGraphError("graph output exceeds bounded response size")
    return result


def execute_capability_graph_json(raw: bytes) -> dict[str, Any]:
    return execute_capability_graph(_read_json(raw))


__all__ = [
    "SCHEMA", "MAX_GRAPH_NODES", "MAX_GRAPH_BYTES",
    "CapabilityGraphError", "execute_capability_graph",
    "execute_capability_graph_json",
]

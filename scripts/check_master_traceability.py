#!/usr/bin/env python3
"""Validate the canonical sharded master traceability graph and resolve change impact."""

from __future__ import annotations

import argparse
from fnmatch import fnmatch
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INDEX = Path("machine/master_traceability.json")
MASTER = Path("machine/ai_master_plan.json")

_FIELD_TYPES = (
    ("requirements", "REQ", "requirement"),
    ("capabilities", "CAP", "capability"),
    ("contracts", "CON", "contract"),
    ("implementation_paths", "PATH", "implementation_path"),
    ("tests", "TEST", "test"),
    ("evaluations", "EVAL", "evaluation"),
    ("evidence", "EVID", "evidence"),
    ("risks", "RISK", "risk"),
    ("gaps", "GAP", "gap"),
)


class TraceabilityError(RuntimeError):
    pass


def _load(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TraceabilityError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise TraceabilityError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(data, dict):
        raise TraceabilityError(f"{relative} must contain an object")
    return data


def _repo_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise TraceabilityError(f"invalid repository path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise TraceabilityError(f"invalid repository path: {value!r}")
    return pure.as_posix()


def _node_id(prefix: str, volume_ref: str, index: int) -> str:
    return f"{prefix}:{volume_ref}:{index + 1:03d}"


def _expected_volume(volume: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    volume_ref = volume["key"]
    volume_id = f"VOL:{volume_ref}"
    nodes: list[dict[str, Any]] = [
        {
            "id": volume_id,
            "type": "volume",
            "volume_ref": volume_ref,
            "title": volume["title"],
            "status": volume["status"],
            "implementation_status": volume["implementation_status"],
            "depth_pass": volume["depth_pass"],
        }
    ]
    edges: list[dict[str, str]] = []
    ids: dict[str, list[str]] = {}
    for field, prefix, node_type in _FIELD_TYPES:
        values = volume.get(field, [])
        if not isinstance(values, list):
            raise TraceabilityError(f"{volume_ref}.{field} must be a list")
        ids[field] = []
        for index, value in enumerate(values):
            node_id = _node_id(prefix, volume_ref, index)
            ids[field].append(node_id)
            nodes.append(
                {
                    "id": node_id,
                    "type": node_type,
                    "volume_ref": volume_ref,
                    "value": value,
                }
            )
            edges.append(
                {
                    "from": volume_id,
                    "to": node_id,
                    "type": f"volume_{node_type}",
                }
            )

    for requirement in ids["requirements"]:
        for test in ids["tests"]:
            edges.append(
                {
                    "from": requirement,
                    "to": test,
                    "type": "requirement_accepted_by_test",
                }
            )
        for evidence in ids["evidence"]:
            edges.append(
                {
                    "from": requirement,
                    "to": evidence,
                    "type": "requirement_supported_by_evidence",
                }
            )
    for capability in ids["capabilities"]:
        for contract in ids["contracts"]:
            edges.append(
                {
                    "from": capability,
                    "to": contract,
                    "type": "capability_bound_by_contract",
                }
            )
    for contract in ids["contracts"]:
        for path in ids["implementation_paths"]:
            edges.append(
                {
                    "from": contract,
                    "to": path,
                    "type": "contract_materialized_at",
                }
            )
    for path in ids["implementation_paths"]:
        for test in ids["tests"]:
            edges.append(
                {
                    "from": path,
                    "to": test,
                    "type": "implementation_validated_by_test",
                }
            )

    nodes.sort(key=lambda item: item["id"])
    edges.sort(key=lambda item: (item["from"], item["type"], item["to"]))
    return nodes, edges


def _matches_implementation_path(changed: str, declared: object) -> bool:
    if not isinstance(declared, str) or not declared:
        return False
    value = declared.strip().replace("\\", "/").rstrip("/")
    if not value or value.startswith("planned:") or "://" in value:
        return False
    if any(char in value for char in "*?["):
        return fnmatch(changed, value)
    if changed == value:
        return True
    return changed.startswith(value + "/")


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    index = _load(root, INDEX)
    master = _load(root, MASTER)
    if index.get("status") != "active":
        raise TraceabilityError("traceability graph must be active")

    binding = index.get("masterplan_binding")
    if not isinstance(binding, dict):
        raise TraceabilityError("masterplan_binding must be an object")
    volume_112 = next(
        (
            volume
            for volume in master.get("volumes", [])
            if isinstance(volume, dict) and volume.get("key") == "VOL-112"
        ),
        None,
    )
    if not isinstance(volume_112, dict) or binding.get("title") != volume_112.get("title"):
        raise TraceabilityError("trace graph must remain bound to VOL-112")
    for gap in binding.get("required_gap_texts", []):
        if gap not in volume_112.get("gaps", []):
            raise TraceabilityError(f"VOL-112 masterplan gap drift: {gap!r}")

    source = index.get("source")
    if not isinstance(source, dict):
        raise TraceabilityError("source must be an object")
    if source.get("master_plan") != "machine/ai_master_plan.json":
        raise TraceabilityError("trace source must be canonical masterplan")
    if source.get("plan_version") != master.get("plan_version"):
        raise TraceabilityError("trace graph masterplan version drift")
    volumes = master.get("volumes")
    if not isinstance(volumes, list) or not volumes:
        raise TraceabilityError("masterplan volumes must be non-empty")
    if source.get("volume_count") != len(volumes):
        raise TraceabilityError("trace source volume_count drift")

    shards = index.get("shards")
    if not isinstance(shards, list) or not shards:
        raise TraceabilityError("trace shards must be non-empty")
    if len(shards) != len({item.get("path") for item in shards if isinstance(item, dict)}):
        raise TraceabilityError("trace shard paths must be unique")

    expected_by_depth: dict[str, list[dict[str, Any]]] = {}
    for volume in volumes:
        if not isinstance(volume, dict):
            raise TraceabilityError("masterplan volume must be an object")
        depth = volume.get("depth_pass")
        if not isinstance(depth, str) or not depth:
            raise TraceabilityError(f"{volume.get('key')} lacks depth_pass")
        expected_by_depth.setdefault(depth, []).append(volume)

    seen_depths: set[str] = set()
    seen_volumes: set[str] = set()
    all_nodes: dict[str, dict[str, Any]] = {}
    all_edges: set[tuple[str, str, str]] = set()
    implementation_nodes: list[dict[str, Any]] = []

    for meta in shards:
        if not isinstance(meta, dict):
            raise TraceabilityError("shard metadata must be an object")
        depth = meta.get("depth_pass")
        if not isinstance(depth, str) or not depth:
            raise TraceabilityError("shard depth_pass must be non-empty")
        if depth in seen_depths:
            raise TraceabilityError(f"duplicate trace shard depth: {depth}")
        seen_depths.add(depth)
        path = _repo_path(meta.get("path"))
        if not path.startswith("machine/traceability/") or not path.endswith(".json"):
            raise TraceabilityError(f"invalid trace shard path: {path}")
        shard = _load(root, Path(path))
        if shard.get("schema_version") != "skeleton.traceability.shard.v1":
            raise TraceabilityError(f"{path} schema_version drift")
        if shard.get("depth_pass") != depth:
            raise TraceabilityError(f"{path} depth_pass drift")

        expected_volumes = expected_by_depth.get(depth)
        if expected_volumes is None:
            raise TraceabilityError(f"{path} references unknown depth pass {depth}")
        expected_refs = [volume["key"] for volume in expected_volumes]
        if shard.get("volume_refs") != expected_refs:
            raise TraceabilityError(f"{path} volume_refs drift")
        if meta.get("volume_count") != len(expected_refs):
            raise TraceabilityError(f"{path} volume_count drift")

        expected_nodes: list[dict[str, Any]] = []
        expected_edges: list[dict[str, str]] = []
        for volume in expected_volumes:
            nodes, edges = _expected_volume(volume)
            expected_nodes.extend(nodes)
            expected_edges.extend(edges)
        expected_nodes.sort(key=lambda item: item["id"])
        expected_edges.sort(key=lambda item: (item["from"], item["type"], item["to"]))

        actual_nodes = shard.get("nodes")
        actual_edges = shard.get("edges")
        if actual_nodes != expected_nodes:
            raise TraceabilityError(f"{path} node content is stale or non-deterministic")
        if actual_edges != expected_edges:
            raise TraceabilityError(f"{path} edge content is stale or non-deterministic")
        if meta.get("node_count") != len(actual_nodes):
            raise TraceabilityError(f"{path} node_count drift")
        if meta.get("edge_count") != len(actual_edges):
            raise TraceabilityError(f"{path} edge_count drift")

        local_ids = {node["id"] for node in actual_nodes}
        if len(local_ids) != len(actual_nodes):
            raise TraceabilityError(f"{path} contains duplicate node ids")
        for edge in actual_edges:
            if edge["from"] not in local_ids or edge["to"] not in local_ids:
                raise TraceabilityError(f"{path} contains dangling edge {edge!r}")
            key = (edge["from"], edge["type"], edge["to"])
            if key in all_edges:
                raise TraceabilityError(f"duplicate global trace edge {key!r}")
            all_edges.add(key)
        for node in actual_nodes:
            node_id = node["id"]
            if node_id in all_nodes:
                raise TraceabilityError(f"duplicate global trace node {node_id}")
            all_nodes[node_id] = node
            if node.get("type") == "implementation_path":
                implementation_nodes.append(node)
        for ref in expected_refs:
            if ref in seen_volumes:
                raise TraceabilityError(f"volume {ref} appears in multiple shards")
            seen_volumes.add(ref)

    if seen_depths != set(expected_by_depth):
        missing = sorted(set(expected_by_depth) - seen_depths)
        extra = sorted(seen_depths - set(expected_by_depth))
        raise TraceabilityError(f"trace shard depth coverage drift missing={missing} extra={extra}")
    expected_volume_refs = {volume["key"] for volume in volumes}
    if seen_volumes != expected_volume_refs:
        missing = sorted(expected_volume_refs - seen_volumes)
        extra = sorted(seen_volumes - expected_volume_refs)
        raise TraceabilityError(f"trace volume coverage drift missing={missing} extra={extra}")

    requirement_ids = {
        node_id
        for node_id, node in all_nodes.items()
        if node.get("type") == "requirement"
    }
    tested = {
        source
        for source, edge_type, _ in all_edges
        if edge_type == "requirement_accepted_by_test"
    }
    evidenced = {
        source
        for source, edge_type, _ in all_edges
        if edge_type == "requirement_supported_by_evidence"
    }
    summary = index.get("summary")
    expected_summary = {
        "node_count": len(all_nodes),
        "edge_count": len(all_edges),
        "requirement_count": len(requirement_ids),
        "requirements_without_evidence": len(requirement_ids - evidenced),
        "shard_count": len(shards),
    }
    if summary != expected_summary:
        raise TraceabilityError(
            f"trace summary drift expected={expected_summary!r} actual={summary!r}"
        )
    requirements_without_tests = sorted(requirement_ids - tested)

    return {
        "status": "valid",
        "node_count": len(all_nodes),
        "edge_count": len(all_edges),
        "volume_count": len(seen_volumes),
        "requirement_count": len(requirement_ids),
        "requirements_without_tests": requirements_without_tests,
        "requirements_without_evidence_count": len(requirement_ids - evidenced),
        "implementation_nodes": implementation_nodes,
        "masterplan_binding": "VOL-112",
    }


def impact(root: Path, changed_files: list[str]) -> dict[str, Any]:
    result = validate(root)
    implementation_nodes = result.pop("implementation_nodes")
    normalized: list[str] = []
    impacted: dict[str, list[str]] = {}
    unmapped: list[str] = []
    for raw in changed_files:
        changed = _repo_path(raw)
        normalized.append(changed)
        refs = sorted(
            {
                node["volume_ref"]
                for node in implementation_nodes
                if _matches_implementation_path(changed, node.get("value"))
            }
        )
        if refs:
            impacted[changed] = refs
        else:
            unmapped.append(changed)
    return {
        **result,
        "changed_files": normalized,
        "impacted": impacted,
        "impacted_volume_refs": sorted({ref for refs in impacted.values() for ref in refs}),
        "unmapped_changed_files": unmapped,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--fail-unmapped", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo_root)
    try:
        result = (
            impact(root, args.changed_file)
            if args.changed_file
            else validate(root)
        )
        result.pop("implementation_nodes", None)
        if args.fail_unmapped and result.get("unmapped_changed_files"):
            raise TraceabilityError(
                "changed files lack implementation-path trace edges: "
                + ", ".join(result["unmapped_changed_files"])
            )
    except TraceabilityError as exc:
        print(f"master traceability: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "master traceability: OK "
            f"({result['volume_count']} volumes, {result['node_count']} nodes, "
            f"{result['edge_count']} edges)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

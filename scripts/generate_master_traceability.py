#!/usr/bin/env python3
"""Regenerate the canonical sharded master traceability graph deterministically."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "machine" / "ai_master_plan.json"
INDEX = ROOT / "machine" / "master_traceability.json"

FIELD_TYPES = (
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


class GenerationError(RuntimeError):
    pass


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GenerationError(f"cannot read {path.relative_to(ROOT)}") from exc
    if not isinstance(value, dict):
        raise GenerationError(f"{path.relative_to(ROOT)} must contain an object")
    return value


def node_id(prefix: str, volume_ref: str, index: int) -> str:
    return f"{prefix}:{volume_ref}:{index + 1:03d}"


def expected_volume(
    volume: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    volume_ref = str(volume["key"])
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

    for field, prefix, node_type in FIELD_TYPES:
        values = volume.get(field, [])
        if not isinstance(values, list):
            raise GenerationError(f"{volume_ref}.{field} must be a list")
        ids[field] = []
        for index, value in enumerate(values):
            current = node_id(prefix, volume_ref, index)
            ids[field].append(current)
            nodes.append(
                {
                    "id": current,
                    "type": node_type,
                    "volume_ref": volume_ref,
                    "value": value,
                }
            )
            edges.append(
                {
                    "from": volume_id,
                    "to": current,
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


def canonical_text(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def build() -> tuple[dict[str, Any], dict[Path, dict[str, Any]]]:
    master = load(MASTER)
    index = load(INDEX)
    volumes = master.get("volumes")
    shards = index.get("shards")
    if not isinstance(volumes, list) or not volumes:
        raise GenerationError("masterplan volumes must be a non-empty list")
    if not isinstance(shards, list) or not shards:
        raise GenerationError("traceability index shards must be non-empty")

    by_depth: dict[str, list[dict[str, Any]]] = {}
    for volume in volumes:
        if not isinstance(volume, dict):
            raise GenerationError("masterplan volume must be an object")
        depth = volume.get("depth_pass")
        if not isinstance(depth, str) or not depth:
            raise GenerationError(f"{volume.get('key')}: missing depth_pass")
        by_depth.setdefault(depth, []).append(volume)

    generated: dict[Path, dict[str, Any]] = {}
    all_nodes: list[dict[str, Any]] = []
    all_edges: list[dict[str, str]] = []

    for meta in shards:
        if not isinstance(meta, dict):
            raise GenerationError("traceability shard metadata must be objects")
        depth = meta.get("depth_pass")
        path_raw = meta.get("path")
        if not isinstance(depth, str) or depth not in by_depth:
            raise GenerationError(f"unknown traceability depth {depth!r}")
        if not isinstance(path_raw, str) or not path_raw.startswith("machine/traceability/"):
            raise GenerationError(f"invalid shard path {path_raw!r}")

        refs = [str(volume["key"]) for volume in by_depth[depth]]
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        for volume in by_depth[depth]:
            volume_nodes, volume_edges = expected_volume(volume)
            nodes.extend(volume_nodes)
            edges.extend(volume_edges)
        nodes.sort(key=lambda item: item["id"])
        edges.sort(key=lambda item: (item["from"], item["type"], item["to"]))

        shard = {
            "schema_version": "skeleton.traceability.shard.v1",
            "depth_pass": depth,
            "volume_refs": refs,
            "nodes": nodes,
            "edges": edges,
        }
        generated[ROOT / path_raw] = shard
        meta["volume_count"] = len(refs)
        meta["node_count"] = len(nodes)
        meta["edge_count"] = len(edges)
        all_nodes.extend(nodes)
        all_edges.extend(edges)

    requirement_ids = {
        node["id"] for node in all_nodes if node.get("type") == "requirement"
    }
    evidenced = {
        edge["from"]
        for edge in all_edges
        if edge.get("type") == "requirement_supported_by_evidence"
    }
    index["source"]["plan_version"] = master.get("plan_version")
    index["source"]["volume_count"] = len(volumes)
    index["summary"] = {
        "node_count": len(all_nodes),
        "edge_count": len(all_edges),
        "requirement_count": len(requirement_ids),
        "requirements_without_evidence": len(requirement_ids - evidenced),
        "shard_count": len(generated),
    }
    return index, generated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        index, shards = build()
    except GenerationError as exc:
        print(f"master traceability generation: rejected: {exc}", file=sys.stderr)
        return 2

    stale: list[str] = []
    expected = {INDEX: index, **shards}
    for path, value in expected.items():
        current = None
        if path.is_file():
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                current = None
        if current != value:
            stale.append(str(path.relative_to(ROOT)))
            if not args.check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(canonical_text(value), encoding="utf-8")

    result = {
        "status": "clean" if not stale else ("stale" if args.check else "regenerated"),
        "changed_files": stale,
        "shard_count": len(shards),
        "node_count": index["summary"]["node_count"],
        "edge_count": index["summary"]["edge_count"],
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "master traceability generation:",
            result["status"],
            f"({len(stale)} changed files)",
        )
    if args.check and stale:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

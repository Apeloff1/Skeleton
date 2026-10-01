#!/usr/bin/env python3
"""Validate and query canonical architecture path ownership."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GRAPH = Path("machine/architecture_ownership.json")
MASTER = Path("machine/ai_master_plan.json")


class ArchitectureOwnershipError(RuntimeError):
    pass


def _load(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArchitectureOwnershipError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise ArchitectureOwnershipError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(data, dict):
        raise ArchitectureOwnershipError(f"{relative} must contain an object")
    return data


def _path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ArchitectureOwnershipError(f"invalid repository path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ArchitectureOwnershipError(f"invalid repository path: {value!r}")
    if pure.as_posix() != value:
        raise ArchitectureOwnershipError(f"non-canonical repository path: {value!r}")
    return value.rstrip("/")


def _matches(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def _resolve(path: str, candidates: list[tuple[str, dict[str, Any]]], label: str) -> dict[str, Any]:
    matches = [(prefix, item) for prefix, item in candidates if _matches(path, prefix)]
    if not matches:
        raise ArchitectureOwnershipError(f"{path} has no declared {label}")
    max_len = max(len(prefix) for prefix, _ in matches)
    best = [(prefix, item) for prefix, item in matches if len(prefix) == max_len]
    if len(best) != 1:
        raise ArchitectureOwnershipError(
            f"{path} has ambiguous {label}: {[prefix for prefix, _ in best]}"
        )
    prefix, item = best[0]
    return {"prefix": prefix, **item}


def build_graph(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    spec = _load(root, GRAPH)
    master = _load(root, MASTER)
    if spec.get("status") != "active":
        raise ArchitectureOwnershipError("ownership graph must be active")

    volumes = {v.get("key"): v for v in master.get("volumes", []) if isinstance(v, dict)}
    bindings = spec.get("masterplan_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ArchitectureOwnershipError("masterplan_bindings must be non-empty")
    refs: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ArchitectureOwnershipError("masterplan binding must be an object")
        ref = binding.get("volume_ref")
        if ref in refs:
            raise ArchitectureOwnershipError(f"duplicate masterplan binding {ref}")
        refs.add(ref)
        volume = volumes.get(ref)
        if not isinstance(volume, dict):
            raise ArchitectureOwnershipError(f"unknown masterplan volume {ref}")
        if binding.get("title") != volume.get("title"):
            raise ArchitectureOwnershipError(f"masterplan title drift for {ref}")
        gaps = binding.get("required_gap_texts")
        if not isinstance(gaps, list) or not gaps:
            raise ArchitectureOwnershipError(f"{ref} gap binding must be non-empty")
        for gap in gaps:
            if gap not in volume.get("gaps", []):
                raise ArchitectureOwnershipError(f"masterplan gap drift for {ref}: {gap!r}")
    if refs != {"VOL-002", "VOL-051"}:
        raise ArchitectureOwnershipError("ownership graph must remain bound to VOL-002 and VOL-051")

    sources = spec.get("sources")
    if not isinstance(sources, dict):
        raise ArchitectureOwnershipError("sources must be an object")
    architecture = _load(root, Path(_path(sources.get("architecture"))))
    ai_tree = _load(root, Path(_path(sources.get("ai_file_tree"))))

    owners: list[tuple[str, dict[str, Any]]] = []
    owner_ids: set[str] = set()
    for item in architecture.get("canonical_roots", []):
        if not isinstance(item, dict):
            raise ArchitectureOwnershipError("canonical root must be an object")
        root_id = item.get("id")
        prefix = _path(item.get("path"))
        if root_id in owner_ids:
            raise ArchitectureOwnershipError(f"duplicate canonical root id {root_id}")
        owner_ids.add(root_id)
        owners.append(
            (
                prefix,
                {
                    "root_id": root_id,
                    "owner": item.get("owner"),
                    "class": item.get("class"),
                    "change_lane": item.get("change_lane"),
                },
            )
        )

    zones: list[tuple[str, dict[str, Any]]] = []
    for zone in architecture.get("zones", []):
        if not isinstance(zone, dict):
            raise ArchitectureOwnershipError("zone must be an object")
        zone_id = zone.get("id")
        for raw in zone.get("roots", []):
            prefix = _path(raw)
            zones.append((prefix, {"zone_id": zone_id}))

    if not owners or not zones:
        raise ArchitectureOwnershipError("architecture must declare owners and zones")

    aliases: list[tuple[str, dict[str, Any]]] = []
    mappings = ai_tree.get("mappings")
    if not isinstance(mappings, list):
        raise ArchitectureOwnershipError("AI file-tree mappings must be a list")
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise ArchitectureOwnershipError("AI file-tree mapping must be an object")
        tags = mapping.get("move_tags", [])
        if not isinstance(tags, list):
            raise ArchitectureOwnershipError(
                f"{mapping.get('id')} move_tags must be a list"
            )
        if "migration:staged-mirror" not in tags:
            continue
        source = _path(mapping.get("source"))
        destination = _path(mapping.get("destination"))
        source_owner = _resolve(source, owners, "canonical owner")
        source_zone = _resolve(source, zones, "architecture zone")
        aliases.append(
            (
                destination,
                {
                    "mapping_id": mapping.get("id"),
                    "source": source,
                    "semantic_owner": source_owner,
                    "semantic_zone": source_zone,
                },
            )
        )

    return {
        "spec": spec,
        "owners": owners,
        "zones": zones,
        "aliases": aliases,
        "ai_tree": ai_tree,
    }


def resolve_path(path: str, root: Path = ROOT) -> dict[str, Any]:
    graph = build_graph(root)
    normalized = _path(path)
    physical_owner = _resolve(normalized, graph["owners"], "canonical owner")
    physical_zone = _resolve(normalized, graph["zones"], "architecture zone")
    alias_matches = [
        (prefix, item)
        for prefix, item in graph["aliases"]
        if _matches(normalized, prefix)
    ]
    semantic_owner = physical_owner
    semantic_zone = physical_zone
    alias = None
    if alias_matches:
        max_len = max(len(prefix) for prefix, _ in alias_matches)
        best = [(prefix, item) for prefix, item in alias_matches if len(prefix) == max_len]
        if len(best) != 1:
            raise ArchitectureOwnershipError(
                f"{normalized} has ambiguous staged-mirror aliases: "
                f"{[prefix for prefix, _ in best]}"
            )
        prefix, alias = best[0]
        semantic_owner = alias["semantic_owner"]
        semantic_zone = alias["semantic_zone"]
        alias = {
            "prefix": prefix,
            "mapping_id": alias["mapping_id"],
            "source": alias["source"],
        }
    return {
        "path": normalized,
        "physical_owner": physical_owner,
        "physical_zone": physical_zone,
        "semantic_owner": semantic_owner,
        "semantic_zone": semantic_zone,
        "staged_mirror_alias": alias,
    }


def validate(root: Path = ROOT) -> dict[str, Any]:
    graph = build_graph(root)
    root = root.resolve()
    mappings = graph["ai_tree"].get("mappings")
    if not isinstance(mappings, list) or not mappings:
        raise ArchitectureOwnershipError("AI file-tree mappings must be non-empty")

    checked = 0
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise ArchitectureOwnershipError("AI file-tree mapping must be an object")
        mapping_id = mapping.get("id")
        for field in ("source", "destination"):
            rel = _path(mapping.get(field))
            if not (root / rel).exists():
                raise ArchitectureOwnershipError(f"{mapping_id} {field} path missing: {rel}")
        source = resolve_path(mapping["source"], root)
        destination = resolve_path(mapping["destination"], root)
        source_owner = source["physical_owner"]["root_id"]
        source_zone = source["physical_zone"]["zone_id"]
        dest_owner = destination["physical_owner"]["root_id"]
        dest_zone = destination["physical_zone"]["zone_id"]
        tags = mapping.get("move_tags", [])
        crosses_boundary = source_owner != dest_owner or source_zone != dest_zone

        if crosses_boundary:
            if "migration:staged-mirror" not in tags:
                raise ArchitectureOwnershipError(
                    f"{mapping_id} crosses owner/zone without staged-mirror contract: "
                    f"{source_owner}/{source_zone} -> {dest_owner}/{dest_zone}"
                )
            if not any(
                isinstance(tag, str) and tag.startswith("cutover:")
                for tag in tags
            ):
                raise ArchitectureOwnershipError(
                    f"{mapping_id} staged mirror lacks cutover disposition"
                )
            disposition = mapping.get("source_disposition")
            if not isinstance(disposition, str) or not disposition.strip():
                raise ArchitectureOwnershipError(
                    f"{mapping_id} staged mirror lacks source_disposition"
                )
            alias = destination.get("staged_mirror_alias")
            if not isinstance(alias, dict) or alias.get("mapping_id") != mapping_id:
                raise ArchitectureOwnershipError(
                    f"{mapping_id} cross-boundary destination lacks exact staged alias"
                )
            if destination["semantic_owner"]["root_id"] != source_owner:
                raise ArchitectureOwnershipError(
                    f"{mapping_id} semantic owner does not preserve source authority"
                )
            if destination["semantic_zone"]["zone_id"] != source_zone:
                raise ArchitectureOwnershipError(
                    f"{mapping_id} semantic zone does not preserve source authority"
                )
        else:
            if destination["semantic_owner"]["root_id"] != source_owner:
                raise ArchitectureOwnershipError(
                    f"{mapping_id} same-boundary mapping changed semantic owner"
                )
            if destination["semantic_zone"]["zone_id"] != source_zone:
                raise ArchitectureOwnershipError(
                    f"{mapping_id} same-boundary mapping changed semantic zone"
                )
        checked += 1

    return {
        "status": "valid",
        "canonical_owner_count": len(graph["owners"]),
        "zone_prefix_count": len(graph["zones"]),
        "staged_mirror_alias_count": len(graph["aliases"]),
        "ai_mapping_count": checked,
        "masterplan_bindings": ["VOL-002", "VOL-051"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--path", help="Resolve one repository path and print its owner/zone.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo_root)
    try:
        result = resolve_path(args.path, root) if args.path else validate(root)
    except ArchitectureOwnershipError as exc:
        print(f"architecture ownership: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json or args.path:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "architecture ownership: OK "
            f"({result['canonical_owner_count']} owners, "
            f"{result['ai_mapping_count']} AI mappings)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

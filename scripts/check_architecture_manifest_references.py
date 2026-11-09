#!/usr/bin/env python3
"""Validate critical manifest references and machine-to-document digest bindings."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY = Path("machine/manifest_reference_policy.json")
MASTER = Path("machine/ai_master_plan.json")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")


class ManifestReferenceError(RuntimeError):
    pass


def _load(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestReferenceError(f"missing required file: {relative}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestReferenceError(f"invalid JSON in {relative}: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestReferenceError(f"{relative} must contain an object")
    return data


def _repo_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ManifestReferenceError(f"invalid repository path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ManifestReferenceError(f"invalid repository path: {value!r}")
    if pure.as_posix() != value:
        raise ManifestReferenceError(f"non-canonical repository path: {value!r}")
    return value


def _pointer(payload: Any, pointer: str) -> Any:
    if pointer == "":
        return payload
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ManifestReferenceError(f"invalid JSON pointer: {pointer!r}")
    current = payload
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise ManifestReferenceError(f"JSON pointer {pointer!r} missing key {token!r}")
            current = current[token]
        elif isinstance(current, list):
            try:
                index = int(token)
            except ValueError as exc:
                raise ManifestReferenceError(f"JSON pointer {pointer!r} has non-index token") from exc
            try:
                current = current[index]
            except IndexError as exc:
                raise ManifestReferenceError(f"JSON pointer {pointer!r} index out of range") from exc
        else:
            raise ManifestReferenceError(f"JSON pointer {pointer!r} traverses scalar")
    return current


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    policy = _load(root, POLICY)
    master = _load(root, MASTER)

    if policy.get("status") != "active":
        raise ManifestReferenceError("manifest reference policy must be active")

    binding = policy.get("masterplan_binding")
    if not isinstance(binding, dict):
        raise ManifestReferenceError("masterplan_binding must be an object")
    volumes = {v.get("key"): v for v in master.get("volumes", []) if isinstance(v, dict)}
    volume = volumes.get(binding.get("volume_ref"))
    if not isinstance(volume, dict):
        raise ManifestReferenceError("unknown masterplan volume binding")
    if binding.get("volume_ref") != "VOL-054" or binding.get("title") != volume.get("title"):
        raise ManifestReferenceError("manifest policy must remain bound to VOL-054")
    gaps = binding.get("required_gap_texts")
    if not isinstance(gaps, list) or not gaps:
        raise ManifestReferenceError("VOL-054 gap bindings must be non-empty")
    for gap in gaps:
        if gap not in volume.get("gaps", []):
            raise ManifestReferenceError(f"VOL-054 masterplan gap drift: {gap!r}")

    groups = policy.get("reference_groups")
    if not isinstance(groups, list) or not groups:
        raise ManifestReferenceError("reference_groups must be non-empty")
    group_ids: set[str] = set()
    checked_references = 0
    for group in groups:
        if not isinstance(group, dict):
            raise ManifestReferenceError("reference group must be an object")
        gid = group.get("id")
        if not isinstance(gid, str) or not gid:
            raise ManifestReferenceError("reference group requires id")
        if gid in group_ids:
            raise ManifestReferenceError(f"duplicate reference group: {gid}")
        group_ids.add(gid)

        manifest_rel = _repo_path(group.get("manifest"))
        manifest = _load(root, Path(manifest_rel))
        value = _pointer(manifest, group.get("json_pointer"))
        kind = group.get("kind")
        values: list[object]
        if kind == "repo_path":
            values = [value]
        elif kind == "repo_path_map":
            if not isinstance(value, dict) or not value:
                raise ManifestReferenceError(f"{gid} pointer must resolve to a non-empty map")
            values = list(value.values())
        else:
            raise ManifestReferenceError(f"{gid} has unsupported kind {kind!r}")

        for raw in values:
            rel = _repo_path(raw)
            checked_references += 1
            if not (root / rel).exists():
                raise ManifestReferenceError(f"{gid} references missing path: {rel}")

    bindings = policy.get("doc_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ManifestReferenceError("doc_bindings must be non-empty")
    seen_sources: set[str] = set()
    seen_docs: set[str] = set()
    for item in bindings:
        if not isinstance(item, dict):
            raise ManifestReferenceError("doc binding must be an object")
        source = _repo_path(item.get("source"))
        doc = _repo_path(item.get("doc"))
        if source in seen_sources:
            raise ManifestReferenceError(f"duplicate doc-binding source: {source}")
        if doc in seen_docs:
            raise ManifestReferenceError(f"duplicate doc-binding document: {doc}")
        seen_sources.add(source)
        seen_docs.add(doc)
        source_path = root / source
        doc_path = root / doc
        if not source_path.is_file():
            raise ManifestReferenceError(f"doc-binding source missing: {source}")
        if not doc_path.is_file():
            raise ManifestReferenceError(f"doc-binding document missing: {doc}")

        digest = _git_blob_sha(source_path)
        if not _SHA1.fullmatch(digest):
            raise ManifestReferenceError(f"internal Git blob digest failure for {source}")
        marker = f"<!-- machine-git-blob: {source}@{digest} -->"
        text = doc_path.read_text(encoding="utf-8")
        occurrences = text.count(marker)
        if occurrences != 1:
            raise ManifestReferenceError(
                f"{doc} must contain exactly one current digest marker for {source}; "
                f"expected {marker!r}, found {occurrences}"
            )
        marker_prefix = f"<!-- machine-git-blob: {source}@"
        if text.count(marker_prefix) != 1:
            raise ManifestReferenceError(
                f"{doc} contains stale/duplicate digest markers for {source}"
            )

    return {
        "status": "valid",
        "reference_group_count": len(groups),
        "checked_reference_count": checked_references,
        "doc_binding_count": len(bindings),
        "masterplan_binding": "VOL-054",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(Path(args.repo_root))
    except ManifestReferenceError as exc:
        print(f"architecture manifest references: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "architecture manifest references: OK "
            f"({result['checked_reference_count']} references, "
            f"{result['doc_binding_count']} digest bindings)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

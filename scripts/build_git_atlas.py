#!/usr/bin/env python3
"""Exhaustive, read-only Git atlas for the canonical repository machine.

Git metadata is authoritative for tracked paths; .machine/repository.toml owns
classification and machine/ai_file_tree.json owns staged AI feature identities.
Indexes are derived artifacts, not new runtime or ownership authorities.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tomllib
from typing import Any

SCHEMA = "skeleton.git-atlas.v1"
MAX_TREE_BYTES = 256 * 1024 * 1024
SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".rs", ".go", ".cpp", ".c", ".h"}
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
HEX_SHA = re.compile(r"[0-9a-f]{40,64}")


def git(root: Path, *arguments: str) -> bytes:
    process = subprocess.run(
        ["git", "-C", str(root), *arguments], capture_output=True, check=False,
        timeout=180,
    )
    if process.returncode:
        raise ValueError(
            f"git {arguments[0]} failed: {process.stderr[:600].decode('utf-8', 'replace')}"
        )
    if len(process.stdout) > MAX_TREE_BYTES:
        raise ValueError("Git metadata exceeds bounded atlas input")
    return process.stdout


def load_authorities(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    policy_file = root / ".machine/repository.toml"
    architecture_file = root / "machine/architecture.json"
    mapping_file = root / "machine/ai_file_tree.json"
    if not all(path.is_file() for path in (policy_file, architecture_file, mapping_file)):
        raise ValueError("canonical repository policy, architecture, and AI tree must exist")
    policy = tomllib.loads(policy_file.read_text(encoding="utf-8"))
    architecture = json.loads(architecture_file.read_text(encoding="utf-8"))
    mappings = json.loads(mapping_file.read_text(encoding="utf-8"))["mappings"]
    zones = policy["zone"]
    if not isinstance(zones, list) or not zones or not architecture.get("canonical_roots"):
        raise ValueError("canonical architecture/zone authority is incomplete")
    if not isinstance(mappings, list):
        raise ValueError("AI tree mapping contract must be a list")
    for zone in zones:
        if not zone.get("name") or not zone.get("owner") or not zone.get("prefixes"):
            raise ValueError("repository machine zone has incomplete ownership")
    return zones, mappings


def classify(path: str, zones: list[dict[str, Any]]) -> tuple[str, str, str]:
    for zone in zones:  # policy order is authoritative (first match wins)
        for prefix in zone["prefixes"]:
            if path == prefix.rstrip("/") or path.startswith(prefix if prefix.endswith("/") else prefix):
                return zone["name"], zone["owner"], zone.get("lifecycle", "unknown")
    return "unclassified", "unclassified", "unclassified"


def feature_identity(path: str, mappings: list[dict[str, Any]], zone: str) -> str:
    candidates: list[tuple[int, str]] = []
    for entry in mappings:
        for field in ("source", "destination"):
            prefix = entry.get(field)
            if not isinstance(prefix, str) or not prefix:
                continue
            if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
                candidates.append((len(prefix), entry["id"]))
    if candidates:
        return max(candidates, key=lambda item: (item[0], item[1]))[1]
    parts = PurePosixPath(path).parts
    if not parts:
        return "unclassified"
    if parts[0] == "satellites" and len(parts) >= 3:
        return "satellites/branch-snapshots" if parts[1] == "branch-snapshots" else "/".join(parts[:2])
    if parts[0] == "skeleton" and len(parts) >= 3:
        return "/".join(parts[:3])
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return zone + "/" + parts[0]


def language(path: str) -> str:
    return {
        ".py": "python", ".ts": "typescript", ".tsx": "typescript",
        ".js": "javascript", ".jsx": "javascript", ".rs": "rust",
        ".go": "go", ".java": "java", ".md": "markdown",
        ".yml": "yaml", ".yaml": "yaml", ".json": "json",
        ".toml": "toml", ".cpp": "cpp", ".c": "c",
    }.get(PurePosixPath(path).suffix.lower(), "other")


def build(root: Path, revision: str = "HEAD") -> tuple[dict[str, Any], list[dict[str, Any]],
                                                        list[dict[str, Any]], dict[str, Any]]:
    root = root.resolve()
    actual_root = Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if actual_root != root:
        raise ValueError("index must run at the actual repository root")
    if revision.startswith("-") or "\x00" in revision:
        raise ValueError("revision must not contain Git options")
    commit = git(root, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}").decode().strip()
    if not HEX_SHA.fullmatch(commit):
        raise ValueError("Git returned an invalid commit identity")
    zones, mappings = load_authorities(root)
    raw = git(root, "ls-tree", "--full-tree", "-r", "-z", "-l", commit)
    authority_paths = {".machine/repository.toml", "machine/architecture.json", "machine/ai_file_tree.json"}
    authority_blobs: dict[str, str] = {}
    for record in raw.split(b"\x00"):
        if not record:
            continue
        metadata, separator, path_bytes = record.partition(b"\t")
        if separator and path_bytes.decode("utf-8", "surrogateescape") in authority_paths:
            fields = metadata.decode("ascii").split()
            if len(fields) != 4 or fields[0] not in ("100644", "100755"):
                raise ValueError("authoritative metadata is not a regular Git blob")
            authority_blobs[path_bytes.decode("utf-8", "surrogateescape")] = fields[2]
    if set(authority_blobs) != authority_paths:
        raise ValueError("missing canonical authority in the pinned Git commit")
    for authority in sorted(authority_paths):
        source = root / authority
        if source.is_symlink():
            raise ValueError("canonical authority cannot be a symbolic link")
        data = source.read_bytes()
        header = f"blob {len(data)}\x00".encode("ascii")
        algorithm = hashlib.sha1 if len(commit) == 40 else hashlib.sha256
        digest = algorithm(header + data).hexdigest()
        if digest != authority_blobs[authority]:
            raise ValueError(f"canonical authority differs from pinned Git commit: {authority}")
    files: list[dict[str, Any]] = []
    hashes: dict[str, list[str]] = defaultdict(list)
    feature_stats: dict[str, dict[str, Any]] = {}
    zone_counts: Counter[str] = Counter()
    root_counts: Counter[str] = Counter()
    lang_counts: Counter[str] = Counter()
    modes: Counter[str] = Counter()
    paths: set[str] = set()
    casefolds: dict[str, str] = {}
    case_collisions: list[list[str]] = []
    total_bytes = 0
    for record in raw.split(b"\x00"):
        if not record:
            continue
        metadata, separator, raw_path = record.partition(b"\t")
        fields = metadata.decode("ascii").split()
        if not separator or len(fields) != 4:
            raise ValueError("malformed Git tree entry")
        mode, entry_type, sha, size_text = fields
        path = raw_path.decode("utf-8", errors="surrogateescape")
        if path in paths or not path or path.startswith("/") or "\x00" in path:
            raise ValueError("duplicate or unsafe Git tree path")
        paths.add(path)
        canonical = path.casefold()
        if canonical in casefolds and casefolds[canonical] != path:
            case_collisions.append([casefolds[canonical], path])
        casefolds.setdefault(canonical, path)
        if entry_type not in ("blob", "commit") or not HEX_SHA.fullmatch(sha):
            raise ValueError("unexpected Git tree entry type/sha")
        size = int(size_text) if size_text != "-" else None
        if size is not None and size < 0:
            raise ValueError("invalid object size")
        zone, owner, lifecycle = classify(path, zones)
        feature = feature_identity(path, mappings, zone)
        lang = language(path)
        is_snapshot = path.startswith("satellites/branch-snapshots/")
        item = {
            "path": path, "mode": mode, "type": entry_type, "blob_sha": sha,
            "size": size, "language": lang, "zone": zone,
            "owner": owner, "lifecycle": lifecycle, "feature": feature,
            "snapshot": is_snapshot,
        }
        files.append(item)
        if entry_type == "blob":
            hashes[sha].append(path)
        zone_counts[zone] += 1
        root_counts[path.split("/", 1)[0]] += 1
        lang_counts[lang] += 1
        modes[mode] += 1
        total_bytes += size or 0
        group = feature_stats.setdefault(feature, {
            "id": feature, "zone": zone, "owner": owner, "files": 0,
            "bytes": 0, "test_files": 0, "example_paths": [],
        })
        group["files"] += 1
        group["bytes"] += size or 0
        if "/test" in path or PurePosixPath(path).name.startswith("test_"):
            group["test_files"] += 1
        if len(group["example_paths"]) < 4:
            group["example_paths"].append(path)
    if not files:
        raise ValueError("empty repository inventory is not accepted")
    files.sort(key=lambda record: record["path"])
    duplicates = [
        {
            "blob_sha": sha, "copies": len(paths), "paths": sorted(paths),
            "snapshot_copies": sum(p.startswith("satellites/branch-snapshots/") for p in paths),
            "disposition": "review_only_never_auto_delete",
        }
        for sha, paths in hashes.items() if len(paths) > 1
    ]
    duplicates.sort(key=lambda group: (-group["copies"], group["blob_sha"]))
    groups = sorted(feature_stats.values(), key=lambda group: (-group["files"], group["id"]))
    token_lookup: dict[str, list[str]] = defaultdict(list)
    for group in sorted(groups, key=lambda item: item["id"]):
        tokens = set(TOKEN.findall(group["id"].lower().replace("-", "_")))
        tokens.update(TOKEN.findall(group["zone"].lower().replace("-", "_")))
        for token in sorted(tokens):
            token_lookup[token].append(group["id"])
    summary = {
        "schema": SCHEMA, "commit": commit, "source": "git-ls-tree",
        "authority": [".machine/repository.toml", "machine/architecture.json",
                      "machine/ai_file_tree.json"],
        "truncated": False, "tracked_entries": len(files),
        "tracked_blobs": sum(item["type"] == "blob" for item in files),
        "gitlinks": modes["160000"], "symlinks": modes["120000"],
        "bytes": total_bytes, "feature_groups": len(groups),
        "exact_duplicate_groups": len(duplicates),
        "extra_exact_copies": sum(group["copies"] - 1 for group in duplicates),
        "snapshot_entries": sum(item["snapshot"] for item in files),
        "case_collisions": case_collisions[:200],
        "case_collision_count": len(case_collisions),
        "zones": dict(sorted(zone_counts.items())),
        "roots": dict(sorted(root_counts.items())),
        "languages": dict(sorted(lang_counts.items())),
        "near_duplicate_status": "not_scanned_use_near_duplicate_milestone",
        "destructive_actions": "prohibited",
    }
    navigation = {
        "schema": SCHEMA, "commit": commit,
        "features": groups, "tokens": dict(sorted(token_lookup.items())),
        "note": "Tokens provide feature-level routing; expand only relevant file records.",
    }
    return summary, files, duplicates, navigation


def write(root: Path, destination: Path, revision: str = "HEAD") -> dict[str, Any]:
    summary, files, duplicates, navigation = build(root, revision)
    if destination.is_symlink():
        raise ValueError("atlas output cannot be a symbolic link")
    destination = destination.resolve()
    if destination == root.resolve() or (root.resolve() / ".git") in destination.parents:
        raise ValueError("cannot overwrite repository root or Git internal data")
    destination.mkdir(parents=True, exist_ok=True)
    def json_bytes(payload: Any) -> bytes:
        return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()
    outputs: dict[str, bytes] = {
        "files.jsonl": b"".join(json_bytes(item) for item in files),
        "exact-duplicates.jsonl": b"".join(json_bytes(item) for item in duplicates),
        "navigation.json": json_bytes(navigation),
    }
    summary["artifacts"] = {
        name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        for name, data in sorted(outputs.items())
    }
    outputs["summary.json"] = json_bytes(summary)
    for name, data in outputs.items():
        target = destination / name
        if target.is_symlink():
            raise ValueError(f"atlas artifact path is a symbolic link: {name}")
        target.write_bytes(data)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", default="HEAD")
    args = parser.parse_args()
    try:
        summary = write(args.root, args.output, args.revision)
    except (ValueError, OSError, subprocess.TimeoutExpired, KeyError, TypeError) as exc:
        print(f"git atlas failed closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "commit": summary["commit"], "tracked_entries": summary["tracked_entries"],
        "feature_groups": summary["feature_groups"],
        "exact_duplicate_groups": summary["exact_duplicate_groups"],
        "extra_exact_copies": summary["extra_exact_copies"],
        "truncated": summary["truncated"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

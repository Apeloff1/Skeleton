"""Exhaustive, read-only, Git-pinned file and feature index.

This complements the working-tree repository machine: no file is opened, a
Git-tracked blob is never executed, and historical/large files are not omitted.
Output is derived only from HEAD; generated reports are disposable artifacts.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from .config import load_machine_config

SCHEMA = "skeleton.repository-git-atlas.v1"
HEADER = re.compile(rb"^(?P<mode>[0-7]{6}) (?P<kind>blob|commit) (?P<oid>[0-9a-f]{40}|[0-9a-f]{64}) +(?P<size>[0-9]+|-)$")
MAX_TREE_BYTES = 100_000_000
MAX_ENTRIES = 500_000


class AtlasError(RuntimeError):
    """Cannot prove an exhaustive or canonical Git inventory."""


def _git(root: Path, *args: str) -> bytes:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("GIT_CONFIG", "GIT_TRACE", "GIT_EXTERNAL_DIFF"))}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        completed = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-c", "diff.external=",
             "-C", str(root), *args],
            check=True, capture_output=True, timeout=120, env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AtlasError(f"Git inventory failed: {type(exc).__name__}") from exc
    if len(completed.stdout) > MAX_TREE_BYTES:
        raise AtlasError("Git response exceeds inventory byte limit")
    return completed.stdout


def _feature(path: str, zone: str, prefixes: tuple[str, ...]) -> str:
    matches = [p for p in prefixes if path == p.rstrip("/") or path.startswith(p)]
    prefix = max(matches, key=len) if matches else ""
    relative = path[len(prefix):].strip("/")
    parts = relative.split("/")
    # Stable within a feature's physical subtree; future explicit IDs can
    # supersede this provisional name when planning a file move.
    sub = "/".join(parts[:2] if len(parts) > 2 else parts[:1])
    return f"{zone}:{sub or 'root'}"


def inventory(root: str | Path) -> dict[str, object]:
    base = Path(root).resolve(strict=True)
    actual = _git(base, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    if Path(actual).resolve() != base:
        raise AtlasError("root must be the exact Git repository root")
    commit = _git(base, "rev-parse", "--verify", "HEAD^{commit}").decode("ascii").strip()
    tree = _git(base, "rev-parse", "--verify", "HEAD^{tree}").decode("ascii").strip()
    raw = _git(base, "ls-tree", "-r", "-z", "-l", "HEAD")
    config = load_machine_config(base)
    records: list[dict[str, object]] = []
    zone_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "bytes": 0})
    features: dict[str, int] = defaultdict(int)
    by_oid: dict[str, list[str]] = defaultdict(list)
    seen: set[str] = set()
    for chunk in raw.split(b"\0"):
        if not chunk:
            continue
        try:
            header, raw_path = chunk.split(b"\t", 1)
        except ValueError as exc:
            raise AtlasError("invalid Git tree record") from exc
        parsed = HEADER.fullmatch(header)
        if not parsed:
            raise AtlasError("unsupported Git tree metadata")
        path = raw_path.decode("utf-8", errors="surrogateescape")
        if not path or path.startswith("/") or any(p in {"", ".", ".."} for p in path.split("/")):
            raise AtlasError("non-canonical Git path")
        if path in seen:
            raise AtlasError("duplicate Git tree path")
        seen.add(path)
        mode = parsed.group("mode").decode("ascii")
        kind = parsed.group("kind").decode("ascii")
        oid = parsed.group("oid").decode("ascii")
        size_text = parsed.group("size")
        if kind == "commit" and (mode != "160000" or size_text != b"-"):
            raise AtlasError("invalid gitlink metadata")
        if kind == "blob" and (mode not in {"100644", "100755", "120000"} or size_text == b"-"):
            raise AtlasError("invalid blob metadata")
        size = int(size_text) if size_text != b"-" else None
        rule = next((item for item in config.zones if item.matches(path)), None)
        zone = rule.name if rule else "unclassified"
        feature = _feature(path, zone, rule.prefixes if rule else ())
        records.append({"path": path, "mode": mode, "type": kind,
                        "blob": oid, "bytes": size, "zone": zone, "feature": feature})
        zone_counts[zone]["files"] += 1
        zone_counts[zone]["bytes"] += size or 0
        features[feature] += 1
        if kind == "blob":
            by_oid[oid].append(path)
        if len(records) > MAX_ENTRIES:
            raise AtlasError("repository exceeds inventory entry bound")
    if not records:
        raise AtlasError("empty Git inventory")
    records.sort(key=lambda item: item["path"])
    duplicates = [
        {"blob": oid, "copies": len(paths), "paths": sorted(paths)}
        for oid, paths in by_oid.items() if len(paths) > 1
    ]
    duplicates.sort(key=lambda item: (-item["copies"], item["blob"]))
    excess = sum(item["copies"] - 1 for item in duplicates)
    summary = {
        "schema": SCHEMA,
        "commit": commit,
        "tree": tree,
        "complete": True,
        "tracked_entries": len(records),
        "blobs": sum(item["type"] == "blob" for item in records),
        "gitlinks": sum(item["type"] == "commit" for item in records),
        "tracked_blob_bytes": sum(item["bytes"] or 0 for item in records),
        "zones": dict(sorted(zone_counts.items())),
        "features": dict(sorted(features.items())),
        "exact_duplicate_groups": len(duplicates),
        "exact_duplicate_excess_paths": excess,
        "classification_contract": ".machine/repository.toml",
        "note": "Byte-identical blobs are not automatically redundant runtime paths.",
    }
    return {"summary": summary, "files": records, "exact_duplicates": duplicates}


def _atomic_write(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


def _json(data: object) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def write_artifacts(result: dict[str, object], output: str | Path) -> dict[str, str]:
    directory = Path(output)
    files = {
        "files.jsonl": b"".join(_json(item) for item in result["files"]),
        "exact-duplicates.json": _json({"schema": SCHEMA, "groups": result["exact_duplicates"]}),
    }
    hashes = {name: hashlib.sha256(contents).hexdigest() for name, contents in files.items()}
    overview = dict(result["summary"])
    overview["artifact_sha256"] = hashes
    files["summary.json"] = _json(overview)
    for name, contents in files.items():
        _atomic_write(directory / name, contents)
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description="Build complete HEAD-pinned repository atlas")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = inventory(args.root)
        write_artifacts(result, args.output)
    except (AtlasError, ValueError, OSError) as exc:
        parser.exit(2, f"repository atlas failed: {exc}\n")
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

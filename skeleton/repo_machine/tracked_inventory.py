"""Pinned-commit, exhaustive tracked-file inventory for the canonical repo machine.

This is a derived, read-only projection. It does not replace the repository
model, read arbitrary working-tree content, or authorize file moves/deletions.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile

from skeleton.repo_intelligence.git_index import GitIndex
from .atlas import placement_for_path
from .config import MachineConfig, load_machine_config


SCHEMA = "skeleton.repo-machine.tracked-atlas.v1"
MODES = {"100644", "100755", "120000", "160000"}
MAX_TREE_BYTES = 64 * 1024 * 1024


class TrackedAtlasError(RuntimeError):
    """An incomplete or ambiguous inventory must fail rather than truncate."""


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def parse_tree(raw: bytes, *, max_files: int = 250_000) -> list[dict[str, object]]:
    """Parse all NUL-separated Git ls-tree entries, including gitlinks/symlinks."""
    if not isinstance(raw, bytes) or len(raw) > MAX_TREE_BYTES:
        raise TrackedAtlasError("Git tree response exceeds configured byte limit")
    if raw and not raw.endswith(b"\0"):
        raise TrackedAtlasError("incomplete Git tree output")
    files: list[dict[str, object]] = []
    seen: set[str] = set()
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, encoded_path = record.split(b"\t", 1)
            mode_b, kind_b, blob_b, size_b = metadata.split()
            mode, kind, object_id = mode_b.decode("ascii"), kind_b.decode("ascii"), blob_b.decode("ascii")
            path = os.fsdecode(encoded_path)
        except (ValueError, UnicodeDecodeError) as exc:
            raise TrackedAtlasError("malformed Git tree record") from exc
        pure = PurePosixPath(path)
        if (
            not path or "\x00" in path or "\\" in path or
            pure.is_absolute() or pure.as_posix() != path or
            any(part in {"", ".", ".."} for part in path.split("/"))
        ):
            raise TrackedAtlasError("unsafe or noncanonical Git path")
        if mode not in MODES or (kind == "blob") != (mode != "160000"):
            raise TrackedAtlasError("unexpected Git object kind or mode")
        if len(object_id) not in (40, 64) or any(c not in "0123456789abcdef" for c in object_id):
            raise TrackedAtlasError("invalid Git object identity")
        if mode == "160000":
            if size_b != b"-":
                raise TrackedAtlasError("gitlink must not expose a blob size")
            size = None
        else:
            if not size_b.isdigit():
                raise TrackedAtlasError("missing blob size")
            size = int(size_b)
        if path in seen:
            raise TrackedAtlasError("duplicate tracked path")
        seen.add(path)
        files.append({"path": path, "mode": mode, "type": kind, "oid": object_id, "size": size})
        if len(files) > max_files:
            raise TrackedAtlasError("tracked file count exceeds configured limit")
    return sorted(files, key=lambda record: os.fsencode(str(record["path"])))


def _feature_family(path: str) -> str:
    """Structural directory family, not a claim of semantic/runtime ownership."""
    parts = PurePosixPath(path).parts
    if len(parts) == 1:
        return "<root>"
    if parts[0] == "satellites" and len(parts) >= 3 and parts[1] == "branch-snapshots":
        return "satellites/branch-snapshots"
    if parts[0] == "skeleton" and len(parts) >= 4 and parts[1] == "ai":
        return "/".join(parts[:4])
    return "/".join(parts[: min(len(parts) - 1, 3)])


def build_artifacts(
    files: list[dict[str, object]],
    config: MachineConfig,
    *,
    commit: str,
    tree: str,
    object_format: str,
) -> dict[str, bytes]:
    if object_format not in {"sha1", "sha256"}:
        raise TrackedAtlasError("unsupported Git object format")
    expected_length = 40 if object_format == "sha1" else 64
    if any(len(str(row["oid"])) != expected_length for row in files):
        raise TrackedAtlasError("mixed or inconsistent Git object formats")
    groups: dict[str, dict[str, object]] = {}
    families: Counter[str] = Counter()
    duplicates: dict[tuple[str, str], list[str]] = defaultdict(list)
    inventory: list[bytes] = []
    total_bytes = 0
    for source in files:
        path = str(source["path"])
        placement = placement_for_path(config, path)
        family = _feature_family(path)
        item = {
            **source,
            "zone": placement.zone,
            "owner": placement.owner,
            "lifecycle": placement.lifecycle,
            "feature_family": family,
        }
        inventory.append(_json_bytes(item))
        zone = groups.setdefault(placement.zone, {
            "owner": placement.owner, "lifecycle": placement.lifecycle,
            "files": 0, "bytes": 0, "families": {},
        })
        zone["files"] += 1
        if source["size"] is not None:
            total_bytes += int(source["size"])
            zone["bytes"] += int(source["size"])
        families[family] += 1
        if source["type"] == "blob":
            duplicates[(str(source["oid"]), str(source["mode"]))].append(path)
    for zone_name, zone in groups.items():
        zone["families"] = dict(sorted(
            (f, count) for f, count in families_for_zone(files, config, zone_name).items()
        ))
    repeated = [
        {"oid": oid, "mode": mode, "paths": sorted(paths), "count": len(paths)}
        for (oid, mode), paths in duplicates.items() if len(paths) > 1
    ]
    repeated.sort(key=lambda row: (-row["count"], row["oid"], row["mode"]))
    manifest = {
        "schema": SCHEMA,
        "source_commit": commit,
        "source_tree": tree,
        "object_format": object_format,
        "tracked_entries": len(files),
        "tracked_blob_bytes": total_bytes,
        "tracked_gitlinks": sum(row["type"] == "commit" for row in files),
        "exact_duplicate_groups": len(repeated),
        "exact_duplicate_paths": sum(row["count"] for row in repeated),
        "groups": len(groups),
        "feature_families": len(families),
        "coverage": "complete",
        "classification": "structural-path-derived",
        "mutation_authority": "none",
    }
    outputs = {
        "files.jsonl": b"".join(inventory),
        "groups.json": _json_bytes({
            "schema": SCHEMA, "groups": dict(sorted(groups.items())),
            "feature_families": dict(sorted(families.items())),
        }),
        "exact-duplicates.json": _json_bytes({"schema": SCHEMA, "groups": repeated}),
    }
    manifest["artifacts"] = {
        name: {"sha256": sha256(content).hexdigest(), "size": len(content)}
        for name, content in sorted(outputs.items())
    }
    outputs["manifest.json"] = _json_bytes(manifest)
    return outputs


def families_for_zone(
    files: list[dict[str, object]], config: MachineConfig, zone: str
) -> Counter[str]:
    return Counter(
        _feature_family(str(item["path"]))
        for item in files
        if placement_for_path(config, str(item["path"])).zone == zone
    )


def build_from_git(root: str | Path, *, max_files: int = 250_000) -> dict[str, bytes]:
    """Pin HEAD before scanning and fail if it changes before publication."""
    git = GitIndex(root, max_files=max_files, timeout_seconds=90)
    commit = git._git(("rev-parse", "--verify", "HEAD")).decode("ascii").strip()
    tree = git._git(("rev-parse", "--verify", commit + "^{tree}")).decode("ascii").strip()
    fmt = git._git(("rev-parse", "--show-object-format")).decode("ascii").strip()
    raw = git._git(("ls-tree", "-r", "-z", "--long", "--full-tree", commit))
    records = parse_tree(raw, max_files=max_files)
    result = build_artifacts(records, load_machine_config(root), commit=commit, tree=tree, object_format=fmt)
    if git._git(("rev-parse", "--verify", "HEAD")).decode("ascii").strip() != commit:
        raise TrackedAtlasError("HEAD changed during inventory")
    return result


def publish(artifacts: dict[str, bytes], output_dir: str | Path, *, check: bool = False) -> None:
    destination = Path(output_dir)
    if check:
        for name, content in artifacts.items():
            path = destination / name
            if not path.is_file() or path.read_bytes() != content:
                raise TrackedAtlasError(f"missing or stale tracked atlas artifact: {name}")
        return
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in artifacts.items():
        with tempfile.NamedTemporaryFile(dir=destination, prefix=".atlas-", delete=False) as tmp:
            try:
                tmp.write(content)
                temp_path = Path(tmp.name)
            except BaseException:
                Path(tmp.name).unlink(missing_ok=True)
                raise
        os.replace(temp_path, destination / name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild/check the exact Git-tree repository atlas")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default=".machine/tracked-inventory")
    parser.add_argument("--max-files", type=int, default=250_000)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        artifacts = build_from_git(args.root, max_files=args.max_files)
        publish(artifacts, args.output, check=args.check)
        summary = json.loads(artifacts["manifest.json"])
        print(json.dumps({
            "commit": summary["source_commit"],
            "files": summary["tracked_entries"],
            "exact_duplicate_groups": summary["exact_duplicate_groups"],
            "groups": summary["groups"],
            "checked": args.check,
        }, sort_keys=True))
    except (TrackedAtlasError, OSError, ValueError) as exc:
        print(f"tracked atlas: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

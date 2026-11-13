#!/usr/bin/env python3
"""Deterministic, non-destructive reconciliation of the governed AI mirror tree.

Unlike a broad copy or generated code replacement, this tool only copies
Git-tracked, manifest-governed files that are *absent* from a staged mirror.
It never replaces an existing implementation, facade or destination overlay.
The canonical AI-tree validator remains the final authority for parity.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = "machine/ai_file_tree.json"


def _safe_path(root: Path, name: str) -> Path:
    """Reject traversal, backslashes and links escaping the repository."""
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("invalid manifest path")
    candidate = PurePosixPath(name)
    # Validate raw path segments before PurePosixPath collapses "." or "//".
    if candidate.is_absolute() or any(p in {"", ".", ".."} for p in name.split("/")):
        raise ValueError("unsafe manifest path")
    path = root.joinpath(*candidate.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("manifest path escapes checkout")
    return path


def _tracked_paths(root: Path) -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return {p.decode("utf-8") for p in result.stdout.split(b"\x00") if p}


def _within(relative: str, exclusions: set[str]) -> bool:
    return any(relative == item or relative.startswith(item + "/") for item in exclusions)


def _checksum(path: Path) -> str:
    """Bound memory consumption even for large tracked binary assets."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _equivalent(source: Path, target: Path) -> bool:
    """Treat reformatted Python mirrors as equal if their ASTs are equal."""
    if source.stat().st_size == target.stat().st_size and _checksum(source) == _checksum(target):
        return True
    if source.suffix == ".py" and target.suffix == ".py":
        try:
            a = ast.parse(source.read_text(encoding="utf-8"))
            b = ast.parse(target.read_text(encoding="utf-8"))
            return ast.dump(a, include_attributes=False) == ast.dump(
                b, include_attributes=False
            )
        except (SyntaxError, UnicodeError, OSError):
            return False
    return False


def plan_mirrors(
    root: Path,
    manifest: dict[str, Any],
    tracked: set[str],
    *,
    mapping_ids: set[str] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return deterministic additions and conflicts without writing anything."""
    root = root.resolve()
    missing: dict[str, dict[str, str]] = {}
    conflicts: dict[str, dict[str, str]] = {}
    mappings = manifest.get("mappings")
    if not isinstance(mappings, list):
        raise ValueError("manifest mappings are not a list")
    seen_ids: set[str] = set()
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise ValueError("invalid mapping")
        identity = mapping.get("id")
        if not isinstance(identity, str) or identity in seen_ids:
            raise ValueError("duplicate or invalid mapping ID")
        seen_ids.add(identity)
        if mapping_ids is not None and identity not in mapping_ids:
            continue
        source = mapping.get("source")
        destination = mapping.get("destination")
        _safe_path(root, source)
        _safe_path(root, destination)
        if not str(destination).startswith("skeleton/ai/"):
            raise ValueError("mirror destination outside governed AI root")
        kind = mapping.get("kind")
        if kind not in {"file", "tree"}:
            raise ValueError("unsupported mirror mapping")
        exclusions = set(mapping.get("source_exclusions", ()))
        overlays = set(mapping.get("overlay_children", ()))
        facades = {
            item["path"]
            for item in mapping.get("parity_exceptions", ())
            if isinstance(item, dict) and item.get("mode") == "compatibility_facade"
        }
        if kind == "file":
            names = [(source, destination, "")]
        else:
            prefix = source.rstrip("/") + "/"
            names = [
                (name, destination.rstrip("/") + "/" + name[len(prefix):], name[len(prefix):])
                for name in tracked
                if name.startswith(prefix)
            ]
        if kind == "tree":
            # Expose destination-only files too. Overlays are intentionally
            # separate AI-owned implementations and must not be touched.
            target_prefix = destination.rstrip("/") + "/"
            source_prefix = source.rstrip("/") + "/"
            for dest_rel in sorted(tracked):
                if not dest_rel.startswith(target_prefix):
                    continue
                local = dest_rel[len(target_prefix):]
                if _within(local, overlays):
                    continue
                if source_prefix + local not in tracked:
                    conflicts[dest_rel] = {
                        "source": source_prefix + local,
                        "destination": dest_rel,
                        "reason": "destination has no tracked canonical source",
                    }
        for src_rel, dest_rel, local in sorted(names):
            if kind == "tree" and (_within(local, exclusions) or _within(local, overlays)):
                continue
            if src_rel not in tracked:
                continue
            original = _safe_path(root, src_rel)
            target = _safe_path(root, dest_rel)
            if original.is_symlink() or not original.is_file():
                raise ValueError("tracked source is not a regular file")
            if target.is_symlink():
                raise ValueError("destination symlink is prohibited")
            if target.exists():
                if mapping.get("parity_mode") != "compatibility_facade" and local not in facades and not _equivalent(original, target):
                    conflicts[dest_rel] = {
                        "source": src_rel, "destination": dest_rel,
                        "reason": "existing destination differs; never overwrite",
                    }
                continue
            digest = _checksum(original)
            entry = {
                "source": src_rel, "destination": dest_rel,
                "source_sha256": digest, "mapping": identity,
            }
            if dest_rel in missing and missing[dest_rel]["source_sha256"] != digest:
                raise ValueError("overlapping mappings disagree on mirror content")
            missing[dest_rel] = entry
    if mapping_ids is not None and mapping_ids - seen_ids:
        raise ValueError("requested mapping ID does not exist")
    return [missing[key] for key in sorted(missing)], [
        conflicts[key] for key in sorted(conflicts)
    ]


def apply_mirrors(root: Path, additions: list[dict[str, str]]) -> int:
    """Atomically create only missing files; never replace a destination."""
    count = 0
    for entry in additions:
        src = _safe_path(root, entry["source"])
        dst = _safe_path(root, entry["destination"])
        if _checksum(src) != entry["source_sha256"]:
            raise ValueError("source changed since plan was computed")
        if dst.exists() or dst.is_symlink():
            raise FileExistsError("destination changed since plan")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.parent.resolve().is_relative_to(root.resolve()):
            raise ValueError("destination parent escapes checkout")
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=dst.parent, delete=False) as temp:
                temp_name = temp.name
                with src.open("rb") as stream:
                    shutil.copyfileobj(stream, temp)
            # The canonical file may have changed between the pre-copy digest
            # and streaming the bytes. Verify the staged artifact itself before
            # exposing its path; never publish bytes that lack plan authority.
            if _checksum(Path(temp_name)) != entry["source_sha256"]:
                raise ValueError("staged mirror differs from planned source digest")
            os.chmod(temp_name, stat.S_IMODE(src.stat().st_mode))
            # A hard link creates the name exclusively and atomically on the
            # same filesystem; an existing destination is never clobbered.
            os.link(temp_name, dst)
            count += 1
        finally:
            if temp_name is not None:
                Path(temp_name).unlink(missing_ok=True)
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--mapping", action="append", default=[])
    parser.add_argument("--apply", action="store_true", help="atomically create missing mirrors")
    parser.add_argument("--max-additions", type=int, default=1000)
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        manifest_path = _safe_path(root, args.manifest)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        additions, conflicts = plan_mirrors(
            root, manifest, _tracked_paths(root),
            mapping_ids=set(args.mapping) if args.mapping else None,
        )
        if args.max_additions < 1 or len(additions) > args.max_additions:
            raise ValueError("planned mirror additions exceed the explicit transaction limit")
        if args.apply and not conflicts:
            applied = apply_mirrors(root, additions)
        else:
            applied = 0
        receipt = {
            "schema_version": "skeleton.ai-tree-mirror-sync.v1",
            "mode": "apply" if args.apply else "check",
            "planned": len(additions),
            "applied": applied,
            "conflicts": conflicts,
            "additions": additions,
        }
        encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        receipt["receipt_sha256"] = hashlib.sha256(encoded).hexdigest()
        print(json.dumps(receipt, sort_keys=True, indent=2))
        return 1 if conflicts or (not args.apply and additions) else 0
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"AI-tree mirror synchronization failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

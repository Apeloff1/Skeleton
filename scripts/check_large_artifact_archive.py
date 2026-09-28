#!/usr/bin/env python3
"""Validate archived oversized payload metadata and current-tree size policy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "machine" / "large_artifact_archive.json"
THRESHOLD_BYTES = 10 * 1024 * 1024
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_CLASSES = {
    "branch-snapshot-archival-binary",
    "branch-snapshot-archival-media",
    "branch-snapshot-archival-backup",
    "legacy-runtime-backup",
}
ENTRY_KEYS = {
    "path",
    "blob_sha",
    "size",
    "classification",
    "required_for_build",
    "recovery",
    "replacement_reference",
}


class LargeArtifactArchiveError(ValueError):
    """The large-artifact archive contract is malformed or stale."""


def _safe_relative(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise LargeArtifactArchiveError(f"{field} must be a non-empty trimmed string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise LargeArtifactArchiveError(f"{field} must be a normalized relative path")
    if "\x00" in value or "\n" in value or "\r" in value:
        raise LargeArtifactArchiveError(f"{field} contains unsafe characters")
    return path.as_posix()


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LargeArtifactArchiveError(f"cannot parse archive manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise LargeArtifactArchiveError("archive manifest must be an object")
    return payload


def validate_payload(
    payload: dict[str, Any],
    *,
    root: Path = ROOT,
) -> tuple[dict[str, Any], ...]:
    expected_top = {
        "schema_version",
        "baseline_git_sha",
        "threshold_bytes",
        "policy",
        "recovery",
        "entries",
    }
    if set(payload) != expected_top:
        raise LargeArtifactArchiveError("archive manifest top-level keys drifted")
    if payload["schema_version"] != 1:
        raise LargeArtifactArchiveError("schema_version must equal 1")
    baseline = payload["baseline_git_sha"]
    if not isinstance(baseline, str) or FULL_SHA.fullmatch(baseline) is None:
        raise LargeArtifactArchiveError("baseline_git_sha must be a full lowercase SHA")
    if payload["threshold_bytes"] != THRESHOLD_BYTES:
        raise LargeArtifactArchiveError("threshold_bytes must remain exactly 10 MiB")
    if payload["policy"] != "docs/ARTIFACT_POLICY.md":
        raise LargeArtifactArchiveError("artifact policy reference drifted")
    if not isinstance(payload["recovery"], str) or not payload["recovery"]:
        raise LargeArtifactArchiveError("recovery instructions are required")

    raw_entries = payload["entries"]
    if not isinstance(raw_entries, list) or not raw_entries:
        raise LargeArtifactArchiveError("entries must be a non-empty list")
    if len(raw_entries) > 100:
        raise LargeArtifactArchiveError("archive entry count exceeds policy bound")

    seen_paths: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, dict) or set(raw) != ENTRY_KEYS:
            raise LargeArtifactArchiveError(f"entry {index} keys drifted")
        path = _safe_relative(raw["path"], field=f"entry {index} path")
        if path in seen_paths:
            raise LargeArtifactArchiveError(f"duplicate archive path: {path}")
        seen_paths.add(path)

        blob_sha = raw["blob_sha"]
        if not isinstance(blob_sha, str) or FULL_SHA.fullmatch(blob_sha) is None:
            raise LargeArtifactArchiveError(f"{path}: blob_sha must be a full lowercase SHA")
        size = raw["size"]
        if isinstance(size, bool) or not isinstance(size, int) or size <= THRESHOLD_BYTES:
            raise LargeArtifactArchiveError(f"{path}: archived size must exceed 10 MiB")
        if raw["classification"] not in ALLOWED_CLASSES:
            raise LargeArtifactArchiveError(f"{path}: unsupported classification")
        if raw["required_for_build"] is not False:
            raise LargeArtifactArchiveError(f"{path}: archived payload cannot be a live build input")
        if raw["recovery"] != "git-history":
            raise LargeArtifactArchiveError(f"{path}: recovery must remain git-history")

        replacement = raw["replacement_reference"]
        if replacement is not None:
            replacement = _safe_relative(
                replacement,
                field=f"{path} replacement_reference",
            )
            if not (root / replacement).is_file():
                raise LargeArtifactArchiveError(
                    f"{path}: replacement reference is missing: {replacement}"
                )
        if (root / path).exists():
            raise LargeArtifactArchiveError(
                f"{path}: oversized payload was restored to the working tree"
            )

        normalized.append(
            {
                **raw,
                "path": path,
                "replacement_reference": replacement,
            }
        )
    return tuple(normalized)


def _ls_tree(root: Path, revision: str) -> list[tuple[str, str, int]]:
    try:
        result = subprocess.run(
            ["git", "ls-tree", "-r", "-l", revision],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise LargeArtifactArchiveError(
            f"cannot enumerate Git tree {revision}: {exc}"
        ) from exc

    rows: list[tuple[str, str, int]] = []
    for line in result.stdout.splitlines():
        metadata, separator, path = line.partition("\t")
        if not separator:
            continue
        parts = metadata.split()
        if len(parts) != 4 or parts[1] != "blob":
            continue
        _, _, blob_sha, raw_size = parts
        try:
            size = int(raw_size)
        except ValueError as exc:
            raise LargeArtifactArchiveError(
                f"invalid Git tree size for {path}: {raw_size}"
            ) from exc
        rows.append((path, blob_sha, size))
    return rows


def current_oversized_blobs(root: Path = ROOT) -> tuple[tuple[str, str, int], ...]:
    return tuple(
        row for row in _ls_tree(root, "HEAD") if row[2] > THRESHOLD_BYTES
    )


def verify_history(
    entries: tuple[dict[str, Any], ...],
    *,
    baseline: str,
    root: Path = ROOT,
) -> None:
    historical = {path: (sha, size) for path, sha, size in _ls_tree(root, baseline)}
    for entry in entries:
        observed = historical.get(entry["path"])
        expected = (entry["blob_sha"], entry["size"])
        if observed != expected:
            raise LargeArtifactArchiveError(
                f"{entry['path']}: baseline Git object mismatch"
            )


def validate_repository(
    *,
    root: Path = ROOT,
    manifest_path: Path = MANIFEST,
    verify_historical_objects: bool = False,
) -> tuple[dict[str, Any], ...]:
    payload = load_manifest(manifest_path)
    entries = validate_payload(payload, root=root)
    oversized = current_oversized_blobs(root)
    if oversized:
        preview = ", ".join(f"{path} ({size})" for path, _, size in oversized[:10])
        raise LargeArtifactArchiveError(
            f"working tree still contains blobs over 10 MiB: {preview}"
        )
    if verify_historical_objects:
        verify_history(
            entries,
            baseline=payload["baseline_git_sha"],
            root=root,
        )
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-history", action="store_true")
    args = parser.parse_args()
    try:
        entries = validate_repository(
            verify_historical_objects=args.verify_history,
        )
    except LargeArtifactArchiveError as exc:
        print(f"large-artifact archive: FAIL: {exc}")
        return 1
    archived = sum(entry["size"] for entry in entries)
    print(
        "large-artifact archive: OK "
        f"entries={len(entries)} archived_bytes={archived} current_oversized=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

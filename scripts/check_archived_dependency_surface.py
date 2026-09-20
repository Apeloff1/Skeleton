#!/usr/bin/env python3
"""Reject dependency-manager manifests from archival branch snapshots.

The snapshots under satellites/branch-snapshots are provenance evidence only.
Keeping files under dependency-manager canonical names causes repository-level
security tooling to treat stale historical graphs as live dependency surfaces.
This gate fails closed whenever a newly imported snapshot exposes an installable
manifest or the provenance map drifts from the quarantined files.
"""
from __future__ import annotations

import json
import re
import string
import sys
from pathlib import Path, PurePosixPath
from typing import Any

ARCHIVE_ROOT = Path("satellites/branch-snapshots")
ARCHIVE_MAP = ARCHIVE_ROOT / "DEPENDENCY_ARCHIVE_MAP.json"

EXACT_MANIFEST_NAMES = {
    "package.json",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lock",
    "bun.lockb",
    "pyproject.toml",
    "poetry.lock",
    "pdm.lock",
    "uv.lock",
    "pipfile",
    "pipfile.lock",
    "setup.py",
    "setup.cfg",
    "gemfile",
    "gemfile.lock",
    "go.mod",
    "go.sum",
    "cargo.toml",
    "cargo.lock",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "composer.lock",
}
REQUIREMENTS_RE = re.compile(r"^requirements(?:[-_.][^/]*)?\.txt$", re.IGNORECASE)
ARCHIVE_PREFIX = "satellites/branch-snapshots/"


def is_installable_manifest_name(name: str) -> bool:
    """Return whether *name* is recognized by common dependency tooling."""
    lowered = name.lower()
    return lowered in EXACT_MANIFEST_NAMES or REQUIREMENTS_RE.fullmatch(name) is not None


def find_installable_manifests(root: Path = ARCHIVE_ROOT) -> list[Path]:
    """Find canonical dependency surfaces below the archival snapshot tree."""
    if not root.is_dir():
        raise FileNotFoundError(f"archival snapshot root is missing: {root}")

    findings: list[Path] = []
    for path in root.rglob("*"):
        if (path.is_file() or path.is_symlink()) and is_installable_manifest_name(path.name):
            findings.append(path)
    return sorted(findings, key=lambda item: item.as_posix())


def _canonical_repo_path(raw: Any) -> PurePosixPath | None:
    if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw:
        return None
    path = PurePosixPath(raw)
    normalized = path.as_posix()
    if (
        path.is_absolute()
        or normalized != raw
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        return None
    return path


def _looks_like_git_blob_sha(raw: Any) -> bool:
    return (
        isinstance(raw, str)
        and len(raw) == 40
        and all(character in string.hexdigits for character in raw)
    )


def validate_archive_map(
    map_path: Path = ARCHIVE_MAP,
    *,
    repo_root: Path = Path("."),
) -> list[str]:
    """Validate provenance-map structure and its working-tree evidence."""
    payload = json.loads(map_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return ["archive map must be an object with schema_version=1"]

    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        return ["archive map entries must be a non-empty list"]

    seen_sources: set[str] = set()
    seen_archives: set[str] = set()

    for index, entry in enumerate(entries):
        label = f"entries[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label}: entry must be an object")
            continue

        source = _canonical_repo_path(entry.get("source_path"))
        archive = _canonical_repo_path(entry.get("archive_path"))
        if source is None:
            errors.append(f"{label}: source_path is not canonical")
        if archive is None:
            errors.append(f"{label}: archive_path is not canonical")
        if source is None or archive is None:
            continue

        source_text = source.as_posix()
        archive_text = archive.as_posix()
        if not source_text.startswith(ARCHIVE_PREFIX):
            errors.append(f"{label}: source_path escapes archive root")
        if not archive_text.startswith(ARCHIVE_PREFIX):
            errors.append(f"{label}: archive_path escapes archive root")
        if not is_installable_manifest_name(source.name):
            errors.append(f"{label}: source_path is not a recognized dependency manifest")
        if is_installable_manifest_name(archive.name):
            errors.append(f"{label}: archive_path still has an installable manifest name")
        if ".snapshot" not in archive.name:
            errors.append(f"{label}: archive_path must carry an explicit .snapshot marker")

        if source_text in seen_sources:
            errors.append(f"{label}: duplicate source_path")
        if archive_text in seen_archives:
            errors.append(f"{label}: duplicate archive_path")
        seen_sources.add(source_text)
        seen_archives.add(archive_text)

        source_fs = repo_root / source_text
        archive_fs = repo_root / archive_text
        if source_fs.exists():
            errors.append(f"{label}: source_path still exists in the working tree")
        if archive_fs.is_symlink():
            errors.append(f"{label}: archive_path must not be a symlink")
            continue
        if not archive_fs.is_file():
            errors.append(f"{label}: archive_path is missing")
            continue

        expected_size = entry.get("size")
        if not isinstance(expected_size, int) or expected_size < 0:
            errors.append(f"{label}: size must be a non-negative integer")
        else:
            try:
                observed_size = archive_fs.stat().st_size
            except OSError as exc:
                errors.append(f"{label}: cannot stat archive_path ({type(exc).__name__})")
            else:
                if observed_size != expected_size:
                    errors.append(
                        f"{label}: archive size mismatch "
                        f"(expected {expected_size}, observed {observed_size})"
                    )

        if not _looks_like_git_blob_sha(entry.get("blob_sha")):
            errors.append(f"{label}: blob_sha must be a 40-character hexadecimal Git blob id")

    vendor_files: set[str] = set()
    archive_root_fs = repo_root / ARCHIVE_ROOT
    if archive_root_fs.is_dir():
        for path in archive_root_fs.rglob("*"):
            if not path.is_file() or "vendor/dependency-manifests" not in path.as_posix():
                continue
            vendor_files.add(path.relative_to(repo_root).as_posix())

    unmapped = sorted(vendor_files - seen_archives)
    missing_from_tree = sorted(seen_archives - vendor_files)
    for path in unmapped:
        errors.append(f"unmapped quarantined dependency evidence: {path}")
    for path in missing_from_tree:
        errors.append(f"mapped archive evidence missing from quarantine tree: {path}")

    return errors


def main() -> int:
    try:
        findings = find_installable_manifests()
        map_errors = validate_archive_map()
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"archived-dependency-surface: cannot inspect archive safely: "
            f"{type(exc).__name__}",
            file=sys.stderr,
        )
        return 2

    if findings:
        print(
            "archived-dependency-surface: installable dependency manifests are "
            "forbidden below satellites/branch-snapshots:",
            file=sys.stderr,
        )
        for path in findings[:100]:
            print(f"  - {path.as_posix()}", file=sys.stderr)
        if len(findings) > 100:
            print(f"  - ... and {len(findings) - 100} more", file=sys.stderr)

    if map_errors:
        print("archived-dependency-surface: provenance-map drift detected:", file=sys.stderr)
        for error in map_errors[:100]:
            print(f"  - {error}", file=sys.stderr)
        if len(map_errors) > 100:
            print(f"  - ... and {len(map_errors) - 100} more", file=sys.stderr)

    if findings or map_errors:
        print(
            "Historical dependency evidence must remain under non-installable "
            "*.snapshot names with a consistent provenance map.",
            file=sys.stderr,
        )
        return 1

    payload = json.loads(ARCHIVE_MAP.read_text(encoding="utf-8"))
    print(
        "archived-dependency-surface: OK "
        f"({len(payload['entries'])} quarantined manifest(s), no live archive surfaces)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

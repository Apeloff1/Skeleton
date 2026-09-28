#!/usr/bin/env python3
"""Restore a tracked large artifact from an immutable Git object manifest.

The manifest identifies the original source commit, Git blob OID, exact byte
size, and destination path. The restorer never trusts filenames from command
arguments beyond the manifest path itself and refuses traversal, symlinked
repository escapes, wrong object types, size drift, or content/OID drift.

If the blob is not present in the local object database, the source commit is
fetched by exact SHA from the configured remote before materialization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Iterable


MANIFEST_SCHEMA = 1
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
EXPECTED_KEYS = frozenset(
    {"schema", "path", "source_commit", "blob_oid", "size_bytes", "kind"}
)


class ArtifactRestoreError(ValueError):
    """The artifact manifest or restored content cannot be trusted."""


def _run_git(
    repo_root: Path,
    args: list[str],
    *,
    stdout: int | Any = subprocess.PIPE,
) -> subprocess.CompletedProcess[Any]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=subprocess.PIPE,
            text=False,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            detail = exc.stderr.decode("utf-8", errors="replace")[:500]
        raise ArtifactRestoreError(
            f"git command failed: {' '.join(args)}{': ' + detail if detail else ''}"
        ) from exc


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ArtifactRestoreError(f"cannot read manifest: {path}") from exc
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ArtifactRestoreError("manifest exceeds maximum size")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactRestoreError("manifest is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ArtifactRestoreError("manifest root must be an object")
    if set(payload) != EXPECTED_KEYS:
        missing = sorted(EXPECTED_KEYS - set(payload))
        extra = sorted(set(payload) - EXPECTED_KEYS)
        raise ArtifactRestoreError(
            f"manifest keys mismatch; missing={missing} extra={extra}"
        )
    if payload["schema"] != MANIFEST_SCHEMA:
        raise ArtifactRestoreError(
            f"unsupported artifact manifest schema: {payload['schema']!r}"
        )
    return payload


def _normalized_relative_path(value: Any) -> Path:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ArtifactRestoreError("artifact path must be a non-empty trimmed string")
    if "\x00" in value or "\n" in value or "\r" in value or "\\" in value:
        raise ArtifactRestoreError("artifact path contains unsafe characters")
    candidate = Path(value)
    if candidate.is_absolute():
        raise ArtifactRestoreError("artifact path must be repository-relative")
    parts = candidate.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ArtifactRestoreError("artifact path contains traversal-like segments")
    return candidate


def _sha1(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or SHA1_RE.fullmatch(value) is None:
        raise ArtifactRestoreError(f"{field} must be a lowercase 40-hex Git SHA-1")
    return value


def _size(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArtifactRestoreError("size_bytes must be an integer")
    if value < 0 or value > MAX_ARTIFACT_BYTES:
        raise ArtifactRestoreError("size_bytes is outside the allowed range")
    return value


def _kind(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ArtifactRestoreError("kind must be a non-empty trimmed string")
    if len(value) > 64 or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value):
        raise ArtifactRestoreError("kind contains unsupported characters")
    return value


def validate_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": MANIFEST_SCHEMA,
        "path": _normalized_relative_path(payload["path"]),
        "source_commit": _sha1(payload["source_commit"], field="source_commit"),
        "blob_oid": _sha1(payload["blob_oid"], field="blob_oid"),
        "size_bytes": _size(payload["size_bytes"]),
        "kind": _kind(payload["kind"]),
    }


def _ensure_blob(
    repo_root: Path,
    *,
    blob_oid: str,
    source_commit: str,
    remote: str,
) -> None:
    probe = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "-e", blob_oid],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if probe.returncode != 0:
        if not remote or remote.startswith("-"):
            raise ArtifactRestoreError("remote name is invalid")
        _run_git(
            repo_root,
            ["fetch", "--no-tags", "--depth=1", remote, source_commit],
            stdout=subprocess.DEVNULL,
        )

    object_type = _run_git(repo_root, ["cat-file", "-t", blob_oid]).stdout
    if object_type.strip() != b"blob":
        raise ArtifactRestoreError("manifest object is not a Git blob")


def check_artifact_manifest(
    manifest_path: Path,
    *,
    repo_root: Path | None = None,
    remote: str = "origin",
) -> dict[str, Any]:
    payload = validate_manifest(_load_manifest(manifest_path))
    root = (repo_root.resolve() if repo_root is not None else _discover_repo_root(manifest_path))
    if not (root / ".git").exists():
        raise ArtifactRestoreError(f"repository root has no .git directory: {root}")

    _ensure_blob(
        root,
        blob_oid=payload["blob_oid"],
        source_commit=payload["source_commit"],
        remote=remote,
    )
    raw_size = _run_git(root, ["cat-file", "-s", payload["blob_oid"]]).stdout.strip()
    try:
        object_size = int(raw_size)
    except ValueError as exc:
        raise ArtifactRestoreError("git returned a non-integer blob size") from exc
    if object_size != payload["size_bytes"]:
        raise ArtifactRestoreError(
            f"artifact object size mismatch: expected {payload['size_bytes']}, got {object_size}"
        )
    return payload


def _git_blob_oid(path: Path, size_bytes: int) -> str:
    digest = hashlib.sha1(usedforsecurity=False)
    digest.update(f"blob {size_bytes}\0".encode("ascii"))
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _discover_repo_root(manifest_path: Path) -> Path:
    resolved = manifest_path.resolve()
    for candidate in (resolved.parent, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    raise ArtifactRestoreError(
        f"cannot discover repository root from manifest: {manifest_path}"
    )


def restore_artifact(
    manifest_path: Path,
    *,
    repo_root: Path | None = None,
    remote: str = "origin",
    overwrite: bool = False,
) -> Path:
    payload = check_artifact_manifest(
        manifest_path,
        repo_root=repo_root,
        remote=remote,
    )
    root = (repo_root.resolve() if repo_root is not None else _discover_repo_root(manifest_path))
    relative = payload["path"]
    destination = root / relative
    destination_parent = destination.parent
    destination_parent.mkdir(parents=True, exist_ok=True)

    resolved_parent = destination_parent.resolve()
    try:
        resolved_parent.relative_to(root)
    except ValueError as exc:
        raise ArtifactRestoreError("artifact destination escapes repository root") from exc

    if destination.exists() and not overwrite:
        raise ArtifactRestoreError(
            f"artifact already exists; use --overwrite to replace: {relative}"
        )
    if destination.is_symlink():
        raise ArtifactRestoreError("artifact destination must not be a symlink")

    _ensure_blob(
        root,
        blob_oid=payload["blob_oid"],
        source_commit=payload["source_commit"],
        remote=remote,
    )

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".artifact-restore-",
            dir=resolved_parent,
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            proc = subprocess.run(
                ["git", "-C", str(root), "cat-file", "blob", payload["blob_oid"]],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=tmp,
                stderr=subprocess.PIPE,
            )
        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", errors="replace")[:500]
            raise ArtifactRestoreError(f"cannot materialize blob: {detail}")

        actual_size = tmp_path.stat().st_size
        if actual_size != payload["size_bytes"]:
            raise ArtifactRestoreError(
                f"artifact size mismatch: expected {payload['size_bytes']}, got {actual_size}"
            )
        actual_oid = _git_blob_oid(tmp_path, actual_size)
        if actual_oid != payload["blob_oid"]:
            raise ArtifactRestoreError(
                f"artifact Git OID mismatch: expected {payload['blob_oid']}, got {actual_oid}"
            )

        os.replace(tmp_path, destination)
        tmp_path = None
        return destination
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="validate manifest and Git object type/size without materializing",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.check_only:
            payload = check_artifact_manifest(
                args.manifest,
                repo_root=args.repo_root,
                remote=args.remote,
            )
            print(
                f"{payload['path']}: {payload['blob_oid']} "
                f"({payload['size_bytes']} bytes)"
            )
            return 0

        restored = restore_artifact(
            args.manifest,
            repo_root=args.repo_root,
            remote=args.remote,
            overwrite=args.overwrite,
        )
    except ArtifactRestoreError as exc:
        print(f"artifact restore failed: {exc}")
        return 1
    print(restored)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

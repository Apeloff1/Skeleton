#!/usr/bin/env python3
"""Verify or materialize immutable artifacts referenced from Git history."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "satellites" / "ARTIFACT_REFERENCES.json"
SCHEMA = 1
MAX_REFERENCES = 256
MAX_MANIFEST_BYTES = 1_048_576
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
ALLOWED_MODES = frozenset({"100644", "100755"})
ENTRY_KEYS = frozenset(
    {
        "id",
        "target_path",
        "source_path",
        "git_blob_oid",
        "sha256",
        "size_bytes",
        "mode",
        "license",
        "redistribution_status",
        "provenance_note",
    }
)


class ArtifactReferenceError(ValueError):
    """Artifact reference metadata or Git provenance is invalid."""


def _git(
    repo_root: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactReferenceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ArtifactReferenceError("artifact reference manifest exceeds size bound")
        with path.open("rb") as handle:
            encoded = handle.read(MAX_MANIFEST_BYTES + 1)
        if len(encoded) > MAX_MANIFEST_BYTES:
            raise ArtifactReferenceError("artifact reference manifest exceeds size bound")
        raw = encoded.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ArtifactReferenceError(
            f"cannot read artifact reference manifest: {path}"
        ) from exc
    try:
        payload = json.loads(raw, object_pairs_hook=_no_duplicate_object)
    except ArtifactReferenceError:
        raise
    except json.JSONDecodeError as exc:
        raise ArtifactReferenceError(f"invalid artifact reference JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ArtifactReferenceError("artifact reference manifest must be an object")
    return payload


def _required_text(value: Any, *, field: str, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ArtifactReferenceError(f"{field} must be a non-empty trimmed string")
    if len(value) > maximum or any(ch in value for ch in ("\x00", "\n", "\r")):
        raise ArtifactReferenceError(f"{field} contains invalid characters or length")
    return value


def _relative_snapshot_path(value: Any, *, field: str) -> str:
    text = _required_text(value, field=field, maximum=4096)
    path = Path(text)
    if path.is_absolute() or text.startswith("/") or text.endswith("/"):
        raise ArtifactReferenceError(f"{field} must be a normalized relative path")
    if "\\" in text or ":" in text or any(part in {"", ".", ".."} for part in text.split("/")):
        raise ArtifactReferenceError(f"{field} contains invalid path segments")
    if not text.startswith("satellites/branch-snapshots/"):
        raise ArtifactReferenceError(
            f"{field} must stay within satellites/branch-snapshots"
        )
    return text


def _positive_size(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ArtifactReferenceError("size_bytes must be a positive integer")
    return value


def _blob_sha256(repo_root: Path, blob_oid: str) -> str:
    process = subprocess.Popen(
        ["git", "cat-file", "blob", blob_oid],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    digest = hashlib.sha256()
    while True:
        chunk = process.stdout.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    _, stderr = process.communicate()
    if process.returncode != 0:
        raise ArtifactReferenceError(
            f"git cat-file failed while hashing {blob_oid}: "
            f"{stderr.decode('utf-8', errors='replace').strip()}"
        )
    return digest.hexdigest()


def _resolve_blob(repo_root: Path, source_commit: str, source_path: str) -> str:
    result = _git(
        repo_root,
        "rev-parse",
        "--verify",
        f"{source_commit}:{source_path}",
        check=False,
    )
    if result.returncode != 0:
        raise ArtifactReferenceError(
            f"cannot resolve source object: {source_commit}:{source_path}"
        )
    oid = result.stdout.decode("ascii", errors="strict").strip()
    if SHA1_RE.fullmatch(oid) is None:
        raise ArtifactReferenceError(
            f"source path did not resolve to a SHA-1 blob: {source_path}"
        )
    kind = _git(repo_root, "cat-file", "-t", oid).stdout.decode("ascii").strip()
    if kind != "blob":
        raise ArtifactReferenceError(f"source object is not a blob: {source_path}")
    return oid


def validate_manifest(
    payload: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    require_targets_removed: bool = True,
) -> tuple[dict[str, Any], ...]:
    if set(payload) != {"schema", "source_commit", "artifacts"}:
        missing = sorted({"schema", "source_commit", "artifacts"} - set(payload))
        extra = sorted(set(payload) - {"schema", "source_commit", "artifacts"})
        raise ArtifactReferenceError(
            f"manifest keys mismatch; missing={missing} extra={extra}"
        )
    if type(payload["schema"]) is not int or payload["schema"] != SCHEMA:
        raise ArtifactReferenceError(
            f"unsupported artifact reference schema: {payload['schema']!r}"
        )
    source_commit = _required_text(payload["source_commit"], field="source_commit")
    if SHA1_RE.fullmatch(source_commit) is None:
        raise ArtifactReferenceError("source_commit must be a 40-character lowercase Git SHA")

    artifacts = payload["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise ArtifactReferenceError("artifacts must be a non-empty list")
    if len(artifacts) > MAX_REFERENCES:
        raise ArtifactReferenceError("artifact reference count exceeds safety bound")

    ids: set[str] = set()
    targets: set[str] = set()
    sha256_by_blob: dict[str, str] = {}
    validated: list[dict[str, Any]] = []
    for index, raw in enumerate(artifacts):
        if not isinstance(raw, dict):
            raise ArtifactReferenceError(f"artifact {index} must be an object")
        missing = sorted(ENTRY_KEYS - set(raw))
        extra = sorted(set(raw) - ENTRY_KEYS)
        if missing or extra:
            raise ArtifactReferenceError(
                f"artifact {index} keys mismatch; missing={missing} extra={extra}"
            )

        artifact_id = _required_text(raw["id"], field="id", maximum=128)
        if ID_RE.fullmatch(artifact_id) is None:
            raise ArtifactReferenceError(f"invalid artifact id: {artifact_id}")
        if artifact_id in ids:
            raise ArtifactReferenceError(f"duplicate artifact id: {artifact_id}")
        ids.add(artifact_id)

        target_path = _relative_snapshot_path(raw["target_path"], field="target_path")
        source_path = _relative_snapshot_path(raw["source_path"], field="source_path")
        if target_path != source_path:
            raise ArtifactReferenceError(
                f"{artifact_id}: source_path must equal the removed target_path"
            )
        if target_path in targets:
            raise ArtifactReferenceError(f"duplicate target_path: {target_path}")
        targets.add(target_path)

        blob_oid = _required_text(raw["git_blob_oid"], field="git_blob_oid")
        if SHA1_RE.fullmatch(blob_oid) is None:
            raise ArtifactReferenceError(
                f"{artifact_id}: git_blob_oid must be a lowercase SHA-1"
            )
        sha256 = _required_text(raw["sha256"], field="sha256")
        if SHA256_RE.fullmatch(sha256) is None:
            raise ArtifactReferenceError(
                f"{artifact_id}: sha256 must be 64 lowercase hex characters"
            )
        size_bytes = _positive_size(raw["size_bytes"])
        mode = _required_text(raw["mode"], field="mode")
        if mode not in ALLOWED_MODES:
            raise ArtifactReferenceError(f"{artifact_id}: unsupported mode {mode!r}")
        license_name = _required_text(raw["license"], field="license", maximum=256)
        redistribution_status = _required_text(
            raw["redistribution_status"], field="redistribution_status", maximum=512
        )
        provenance_note = _required_text(
            raw["provenance_note"], field="provenance_note", maximum=2048
        )

        resolved = _resolve_blob(repo_root, source_commit, source_path)
        if resolved != blob_oid:
            raise ArtifactReferenceError(
                f"{artifact_id}: source path resolves to {resolved}, expected {blob_oid}"
            )
        observed_size = int(
            _git(repo_root, "cat-file", "-s", blob_oid).stdout.decode("ascii").strip()
        )
        if observed_size != size_bytes:
            raise ArtifactReferenceError(
                f"{artifact_id}: blob size {observed_size} != declared {size_bytes}"
            )
        observed_sha256 = sha256_by_blob.get(blob_oid)
        if observed_sha256 is None:
            observed_sha256 = _blob_sha256(repo_root, blob_oid)
            sha256_by_blob[blob_oid] = observed_sha256
        if observed_sha256 != sha256:
            raise ArtifactReferenceError(
                f"{artifact_id}: blob SHA-256 {observed_sha256} != declared {sha256}"
            )

        if require_targets_removed:
            tracked = _git(
                repo_root,
                "ls-files",
                "--error-unmatch",
                "--",
                target_path,
                check=False,
            )
            if tracked.returncode == 0:
                raise ArtifactReferenceError(
                    f"{artifact_id}: target remains tracked; remove the duplicate blob"
                )

        validated.append(
            {
                "id": artifact_id,
                "target_path": target_path,
                "source_path": source_path,
                "git_blob_oid": blob_oid,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "mode": mode,
                "license": license_name,
                "redistribution_status": redistribution_status,
                "provenance_note": provenance_note,
                "source_commit": source_commit,
            }
        )
    return tuple(validated)


def validate_file(
    path: Path = DEFAULT_MANIFEST,
    *,
    repo_root: Path = REPO_ROOT,
    require_targets_removed: bool = True,
) -> tuple[dict[str, Any], ...]:
    return validate_manifest(
        load_manifest(path),
        repo_root=repo_root,
        require_targets_removed=require_targets_removed,
    )


def materialize(
    artifact_id: str,
    output: Path,
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    repo_root: Path = REPO_ROOT,
    force: bool = False,
) -> Path:
    references = validate_file(
        manifest_path,
        repo_root=repo_root,
        require_targets_removed=False,
    )
    match = next((entry for entry in references if entry["id"] == artifact_id), None)
    if match is None:
        raise ArtifactReferenceError(f"unknown artifact id: {artifact_id}")
    if (output.exists() or output.is_symlink()) and not force:
        raise ArtifactReferenceError(f"refusing to overwrite existing path: {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    # Verify a private sibling before publication, preserving the previous
    # output on any subprocess or integrity failure, even with --force.
    descriptor, temporary = tempfile.mkstemp(prefix=".artifact-", dir=output.parent)
    staged = Path(temporary)
    digest = hashlib.sha256()
    written = 0
    process = None
    try:
        with os.fdopen(descriptor, "wb") as handle:
            process = subprocess.Popen(
                ["git", "cat-file", "blob", match["git_blob_oid"]],
                cwd=repo_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert process.stdout is not None
            for chunk in iter(lambda: process.stdout.read(1024 * 1024), b""):
                written += len(chunk)
                if written > match["size_bytes"]:
                    raise ArtifactReferenceError("materialized artifact size mismatch")
                digest.update(chunk)
                handle.write(chunk)
        _, stderr = process.communicate()
        if process.returncode != 0:
            raise ArtifactReferenceError(
                f"git cat-file failed: {stderr.decode('utf-8', errors='replace').strip()}"
            )
        if written != match["size_bytes"]:
            raise ArtifactReferenceError("materialized artifact size mismatch")
        if digest.hexdigest() != match["sha256"]:
            raise ArtifactReferenceError("materialized artifact SHA-256 mismatch")
        observed_oid = _git(repo_root, "hash-object", "--", str(staged.resolve())).stdout.decode("ascii").strip()
        if observed_oid != match["git_blob_oid"]:
            raise ArtifactReferenceError("materialized artifact Git object mismatch")
        staged.chmod(0o755 if match["mode"] == "100755" else 0o644)
        if force:
            os.replace(staged, output)
        else:
            # An existence check alone races with another writer. Linking a
            # sibling publishes atomically and fails if a destination appears.
            try:
                os.link(staged, output)
            except FileExistsError as exc:
                raise ArtifactReferenceError(f"refusing to overwrite existing path: {output}") from exc
        return output
    except (OSError, subprocess.SubprocessError) as exc:
        raise ArtifactReferenceError(f"artifact materialization failed: {exc}") from exc
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate()
        staged.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--materialize", metavar="ARTIFACT_ID")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    if args.materialize:
        if args.output is None:
            print("--output is required with --materialize", file=sys.stderr)
            return 2
        try:
            path = materialize(
                args.materialize,
                args.output,
                manifest_path=args.manifest,
                force=args.force,
            )
        except ArtifactReferenceError as exc:
            print(f"artifact-reference: {exc}", file=sys.stderr)
            return 1
        print(f"artifact-reference: materialized {args.materialize} -> {path}")
        return 0

    try:
        entries = validate_file(args.manifest)
    except ArtifactReferenceError as exc:
        print(f"artifact-reference: {exc}", file=sys.stderr)
        return 1
    print(f"artifact-reference: OK ({len(entries)} immutable reference(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

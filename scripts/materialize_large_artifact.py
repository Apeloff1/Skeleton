#!/usr/bin/env python3
"""Materialize audited legacy artifacts from immutable Git history.

The current source tree intentionally does not carry the large payloads listed
in machine/large_artifacts.json. This command reconstructs a declared legacy
destination only after verifying the pinned source commit/path, Git blob OID,
byte count, SHA-256, destination, and file mode.

Network access is disabled by default. The --fetch-history flag explicitly
permits one bounded git fetch of the pinned source commit when that commit or
blob is not already available locally.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = REPO_ROOT / "machine" / "large_artifacts.json"
MAX_CATALOG_BYTES = 256 * 1024
MAX_ARTIFACTS = 128
MAX_DESTINATIONS = 32
MAX_PATH_LENGTH = 1024
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MODE_RE = re.compile(r"^0[0-7]{3}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
REMOTE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
TOP_LEVEL_KEYS = frozenset(
    {
        "schema",
        "repository",
        "source_commit",
        "git_object_format",
        "integrity_algorithm",
        "fetch_strategy",
        "artifacts",
    }
)
ARTIFACT_KEYS = frozenset(
    {
        "id",
        "source_path",
        "git_blob_oid",
        "sha256",
        "size_bytes",
        "media_type",
        "license",
        "redistribution_status",
        "provenance_note",
        "destinations",
        "mode",
    }
)


class LargeArtifactError(ValueError):
    """The legacy artifact catalog or materialization request is invalid."""


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LargeArtifactError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_catalog(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise LargeArtifactError(f"cannot stat catalog: {path}") from exc
    if size > MAX_CATALOG_BYTES:
        raise LargeArtifactError(
            f"catalog exceeds {MAX_CATALOG_BYTES}-byte safety bound"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise LargeArtifactError(f"cannot read catalog: {path}") from exc
    try:
        payload = json.loads(text, object_pairs_hook=_no_duplicate_object)
    except LargeArtifactError:
        raise
    except json.JSONDecodeError as exc:
        raise LargeArtifactError(f"invalid catalog JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise LargeArtifactError("catalog must be a JSON object")
    return payload


def _text(value: Any, *, field: str, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise LargeArtifactError(f"{field} must be a non-empty trimmed string")
    if len(value) > maximum:
        raise LargeArtifactError(f"{field} exceeds maximum length")
    if any(ch in value for ch in ("\x00", "\n", "\r")):
        raise LargeArtifactError(f"{field} contains unsafe characters")
    return value


def _normalized_repo_path(value: Any, *, field: str) -> str:
    raw = _text(value, field=field, maximum=MAX_PATH_LENGTH)
    if "\\" in raw:
        raise LargeArtifactError(f"{field} must use POSIX separators")
    path = PurePosixPath(raw)
    if path.is_absolute():
        raise LargeArtifactError(f"{field} must be repository-relative")
    if raw in {".", ".."} or any(part in {"", ".", ".."} for part in path.parts):
        raise LargeArtifactError(f"{field} contains traversal-like segments")
    return path.as_posix()


def _positive_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise LargeArtifactError(f"{field} must be a positive integer")
    return value


def load_catalog(path: Path = DEFAULT_CATALOG) -> dict[str, Any]:
    """Load and fail-closed validate the legacy artifact catalog."""

    payload = _read_catalog(path)
    if set(payload) != TOP_LEVEL_KEYS:
        missing = sorted(TOP_LEVEL_KEYS - set(payload))
        extra = sorted(set(payload) - TOP_LEVEL_KEYS)
        raise LargeArtifactError(
            f"catalog keys mismatch; missing={missing} extra={extra}"
        )
    if payload["schema"] != 1:
        raise LargeArtifactError("unsupported large-artifact catalog schema")
    repository = _text(payload["repository"], field="repository")
    if repository != "Apeloff1/Skeleton":
        raise LargeArtifactError("catalog repository identity mismatch")

    source_commit = _text(payload["source_commit"], field="source_commit")
    if SHA1_RE.fullmatch(source_commit) is None:
        raise LargeArtifactError("source_commit must be a lowercase SHA-1")
    if payload["git_object_format"] != "sha1":
        raise LargeArtifactError("unsupported Git object format")
    if payload["integrity_algorithm"] != "sha256":
        raise LargeArtifactError("unsupported artifact integrity algorithm")
    if payload["fetch_strategy"] != "immutable-git-history":
        raise LargeArtifactError("unsupported artifact fetch strategy")

    artifacts = payload["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise LargeArtifactError("artifacts must be a non-empty list")
    if len(artifacts) > MAX_ARTIFACTS:
        raise LargeArtifactError("artifact count exceeds safety bound")

    normalized: list[dict[str, Any]] = []
    ids: set[str] = set()
    destinations_seen: set[str] = set()
    for index, raw in enumerate(artifacts):
        if not isinstance(raw, dict):
            raise LargeArtifactError(f"artifact {index} must be an object")
        if set(raw) != ARTIFACT_KEYS:
            missing = sorted(ARTIFACT_KEYS - set(raw))
            extra = sorted(set(raw) - ARTIFACT_KEYS)
            raise LargeArtifactError(
                f"artifact {index} keys mismatch; missing={missing} extra={extra}"
            )
        artifact_id = _text(raw["id"], field="id", maximum=128)
        if ID_RE.fullmatch(artifact_id) is None:
            raise LargeArtifactError(f"invalid artifact id: {artifact_id}")
        if artifact_id in ids:
            raise LargeArtifactError(f"duplicate artifact id: {artifact_id}")
        ids.add(artifact_id)

        source_path = _normalized_repo_path(raw["source_path"], field="source_path")
        git_blob_oid = _text(raw["git_blob_oid"], field="git_blob_oid")
        if SHA1_RE.fullmatch(git_blob_oid) is None:
            raise LargeArtifactError(
                f"{artifact_id}: git_blob_oid must be a lowercase SHA-1"
            )
        sha256 = _text(raw["sha256"], field="sha256")
        if SHA256_RE.fullmatch(sha256) is None:
            raise LargeArtifactError(
                f"{artifact_id}: sha256 must be 64 lowercase hex characters"
            )
        size_bytes = _positive_int(raw["size_bytes"], field="size_bytes")
        media_type = _text(raw["media_type"], field="media_type", maximum=256)
        license_name = _text(raw["license"], field="license", maximum=256)
        redistribution = _text(
            raw["redistribution_status"],
            field="redistribution_status",
            maximum=512,
        )
        provenance_note = _text(
            raw["provenance_note"],
            field="provenance_note",
            maximum=2048,
        )
        mode = _text(raw["mode"], field="mode", maximum=4)
        if MODE_RE.fullmatch(mode) is None:
            raise LargeArtifactError(f"{artifact_id}: invalid file mode")

        destinations = raw["destinations"]
        if (
            not isinstance(destinations, list)
            or not destinations
            or len(destinations) > MAX_DESTINATIONS
        ):
            raise LargeArtifactError(
                f"{artifact_id}: destinations must be a non-empty bounded list"
            )
        normalized_destinations: list[str] = []
        local_seen: set[str] = set()
        for item in destinations:
            destination = _normalized_repo_path(item, field="destination")
            if destination in local_seen:
                raise LargeArtifactError(
                    f"{artifact_id}: duplicate destination {destination}"
                )
            if destination in destinations_seen:
                raise LargeArtifactError(
                    f"destination assigned to multiple artifacts: {destination}"
                )
            local_seen.add(destination)
            destinations_seen.add(destination)
            normalized_destinations.append(destination)
        if source_path not in local_seen:
            raise LargeArtifactError(
                f"{artifact_id}: source_path must also be a declared destination"
            )

        normalized.append(
            {
                "id": artifact_id,
                "source_path": source_path,
                "git_blob_oid": git_blob_oid,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "media_type": media_type,
                "license": license_name,
                "redistribution_status": redistribution,
                "provenance_note": provenance_note,
                "destinations": tuple(sorted(normalized_destinations)),
                "mode": mode,
            }
        )

    return {
        "schema": 1,
        "repository": repository,
        "source_commit": source_commit,
        "git_object_format": "sha1",
        "integrity_algorithm": "sha256",
        "fetch_strategy": "immutable-git-history",
        "artifacts": tuple(sorted(normalized, key=lambda item: item["id"])),
    }


def _git(
    repo_root: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise LargeArtifactError("Git executable is unavailable") from exc
    except subprocess.CalledProcessError as exc:
        raise LargeArtifactError(f"Git command failed: {' '.join(args)}") from exc


def _object_available(repo_root: Path, spec: str) -> bool:
    result = _git(repo_root, "cat-file", "-e", spec, check=False)
    return result.returncode == 0


def _ensure_source_history(
    repo_root: Path,
    *,
    source_commit: str,
    git_blob_oid: str,
    allow_fetch: bool,
    remote: str,
) -> None:
    commit_spec = f"{source_commit}^{{commit}}"
    blob_spec = f"{git_blob_oid}^{{blob}}"
    if _object_available(repo_root, commit_spec) and _object_available(
        repo_root, blob_spec
    ):
        return
    if not allow_fetch:
        raise LargeArtifactError(
            "pinned source history is not available locally; rerun with "
            "--fetch-history to permit a bounded fetch"
        )

    safe_remote = _text(remote, field="remote", maximum=128)
    if REMOTE_RE.fullmatch(safe_remote) is None:
        raise LargeArtifactError("remote must be a simple named Git remote")
    _git(
        repo_root,
        "fetch",
        "--no-tags",
        "--depth=1",
        safe_remote,
        source_commit,
    )
    if not _object_available(repo_root, commit_spec) or not _object_available(
        repo_root, blob_spec
    ):
        raise LargeArtifactError("pinned source objects remain unavailable after fetch")


def _artifact_by_id(catalog: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    normalized_id = _text(artifact_id, field="artifact id", maximum=128)
    for artifact in catalog["artifacts"]:
        if artifact["id"] == normalized_id:
            return artifact
    raise LargeArtifactError(f"unknown artifact id: {normalized_id}")


def materialize(
    artifact_id: str,
    destination: str,
    *,
    repo_root: Path = REPO_ROOT,
    catalog_path: Path = DEFAULT_CATALOG,
    allow_fetch: bool = False,
    overwrite: bool = False,
    remote: str = "origin",
) -> Path:
    """Materialize one declared legacy path with full integrity verification."""

    repo_root = repo_root.resolve()
    catalog = load_catalog(catalog_path)
    artifact = _artifact_by_id(catalog, artifact_id)
    normalized_destination = _normalized_repo_path(
        destination,
        field="destination",
    )
    if normalized_destination not in artifact["destinations"]:
        raise LargeArtifactError("destination is not declared for this artifact")

    output = (repo_root / normalized_destination).resolve()
    try:
        output.relative_to(repo_root)
    except ValueError as exc:
        raise LargeArtifactError("destination escapes repository root") from exc
    if output.exists() and not overwrite:
        raise LargeArtifactError(
            f"destination already exists: {normalized_destination}"
        )
    if output.is_dir():
        raise LargeArtifactError("destination is a directory")

    source_commit = catalog["source_commit"]
    _ensure_source_history(
        repo_root,
        source_commit=source_commit,
        git_blob_oid=artifact["git_blob_oid"],
        allow_fetch=allow_fetch,
        remote=remote,
    )

    source_spec = f"{source_commit}:{artifact['source_path']}"
    observed_oid = _git(repo_root, "rev-parse", source_spec).stdout.decode().strip()
    if observed_oid != artifact["git_blob_oid"]:
        raise LargeArtifactError(
            f"source path blob mismatch: {observed_oid} != {artifact['git_blob_oid']}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    process = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".partial",
            delete=False,
        ) as handle:
            temp_name = handle.name
            process = subprocess.Popen(
                ["git", "cat-file", "blob", artifact["git_blob_oid"]],
                cwd=repo_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if process.stdout is None:
                raise LargeArtifactError("cannot read Git blob stream")
            digest = hashlib.sha256()
            size = 0
            while True:
                chunk = process.stdout.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > artifact["size_bytes"]:
                    raise LargeArtifactError(
                        "materialized artifact exceeds declared byte count"
                    )
                digest.update(chunk)
                handle.write(chunk)

            stderr = process.stderr.read() if process.stderr is not None else b""
            returncode = process.wait()
            if returncode != 0:
                raise LargeArtifactError(
                    "git cat-file failed while materializing artifact "
                    f"(exit={returncode}, stderr={stderr[:256]!r})"
                )
            if size != artifact["size_bytes"]:
                raise LargeArtifactError(
                    f"artifact size mismatch: {size} != {artifact['size_bytes']}"
                )
            observed_sha256 = digest.hexdigest()
            if observed_sha256 != artifact["sha256"]:
                raise LargeArtifactError(
                    "artifact SHA-256 mismatch: "
                    f"{observed_sha256} != {artifact['sha256']}"
                )

        os.chmod(temp_name, int(artifact["mode"], 8))
        os.replace(temp_name, output)
        temp_name = None
        return output
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if temp_name is not None:
            try:
                Path(temp_name).unlink()
            except FileNotFoundError:
                pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--list", action="store_true", help="list catalog entries")
    parser.add_argument("--artifact", help="artifact id to materialize")
    parser.add_argument(
        "--destination",
        help="one declared repository-relative destination for the artifact",
    )
    parser.add_argument(
        "--fetch-history",
        action="store_true",
        help="permit a bounded fetch of the pinned immutable source commit",
    )
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        catalog = load_catalog(args.catalog)
        if args.list:
            for artifact in catalog["artifacts"]:
                print(
                    f"{artifact['id']}\t{artifact['size_bytes']}\t"
                    f"{artifact['sha256']}\t{artifact['license']}"
                )
            return 0
        if not args.artifact or not args.destination:
            raise LargeArtifactError(
                "--artifact and --destination are required unless --list is used"
            )
        output = materialize(
            args.artifact,
            args.destination,
            catalog_path=args.catalog,
            allow_fetch=args.fetch_history,
            overwrite=args.overwrite,
            remote=args.remote,
        )
    except LargeArtifactError as exc:
        print(f"large-artifact materialization failed: {exc}")
        return 1

    print(f"materialized {output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

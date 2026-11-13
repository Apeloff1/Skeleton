"""Bounded read-only original-content claim inventory for playable game source.

This verifies that an independently pinned, owner-private provenance claim
matches real canonical source bytes and the replay-verified original project.
It does NOT establish copyright, license grants, authorship or plagiarism
clearance; claims are only assertions supplied by a local operator.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import stat
import sys
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_verify import (
    _assert_original_root, _child_fd, _parts, _read, _root_fd,
    verify_exported_package,
)
from skeleton.app.offline_archive_signature import _pin
from skeleton.app.offline_install_reconciliation import _identity
from skeleton.app.offline_source_trust_policy import _read_policy

SCHEMA = "skeleton.app.original_content_provenance_claims.v1"
RECEIPT_SCHEMA = "skeleton.app.original_content_provenance_inspection.v1"
MAX_CLAIMS = 24
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
ORIGINS = frozenset(("ai_generated_original", "human_authored_original"))


class OriginalContentProvenanceError(ValueError):
    """Claim manifest or original game source is not independently bound."""


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise OriginalContentProvenanceError("duplicate provenance claim field")
        result[key] = value
    return result


def _parse(raw: bytes, *, project_id: str, manifest_pin: str) -> list[tuple[str, str, str]]:
    try:
        data = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                OriginalContentProvenanceError("nonfinite provenance value")
            ),
        )
    except (ValueError, TypeError, UnicodeError) as exc:
        raise OriginalContentProvenanceError("invalid provenance claim JSON") from exc
    if (type(data) is not dict or set(data) != {
            "schema", "project_id", "manifest_sha256", "rights_review_status", "files",
        } or data["schema"] != SCHEMA or data["project_id"] != project_id
            or data["manifest_sha256"] != manifest_pin
            or data["rights_review_status"] != "unreviewed"):
        raise OriginalContentProvenanceError("provenance source scope or status mismatch")
    files = data["files"]
    if type(files) is not list or not 2 <= len(files) <= MAX_CLAIMS:
        raise OriginalContentProvenanceError("bounded provenance file inventory required")
    result: list[tuple[str, str, str]] = []
    for item in files:
        if type(item) is not dict or set(item) != {"path", "sha256", "origin"}:
            raise OriginalContentProvenanceError("invalid provenance file claim")
        path = item["path"]
        _parts(path)  # Reject traversal, absolute paths and unsafe components.
        digest = _pin(item["sha256"], "source file")
        origin = item["origin"]
        if type(origin) is not str or origin not in ORIGINS:
            raise OriginalContentProvenanceError("unsupported original-content origin")
        result.append((path, digest, origin))
    paths = [item[0] for item in result]
    if paths != sorted(set(paths)):
        raise OriginalContentProvenanceError("provenance paths must be sorted and unique")
    if not {"index.html", "godot/project.godot"}.issubset(paths):
        raise OriginalContentProvenanceError(
            "browser and Godot source entries both required"
        )
    return result


def _file_identity(fd: int, path: str) -> tuple[int, ...]:
    """Bind both the claimed inode and each path ancestor's directory inode.

    A source directory can be exchanged while its original file inodes are
    moved into the replacement directory. File hashes and file-only inode
    checks cannot distinguish that directory substitution.
    """
    parts = _parts(path)
    ancestor_identity: list[int] = []
    for depth in range(1, len(parts)):
        parent = _child_fd(fd, parts[:depth], directory=True)
        try:
            directory = os.fstat(parent)
            if not stat.S_ISDIR(directory.st_mode):
                raise OriginalContentProvenanceError(
                    "claimed source ancestor is not a directory"
                )
            ancestor_identity.extend((
                directory.st_dev, directory.st_ino, directory.st_ctime_ns,
            ))
        finally:
            os.close(parent)
    handle = _child_fd(fd, parts, directory=False)
    try:
        info = os.fstat(handle)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or info.st_mode & 0o022):
            raise OriginalContentProvenanceError("unsafe claimed source file")
        return tuple(ancestor_identity) + (
            info.st_dev, info.st_ino, info.st_size, info.st_nlink,
            info.st_uid, info.st_mode, info.st_mtime_ns, info.st_ctime_ns,
        )
    finally:
        os.close(handle)


def inspect_original_content_provenance(
    installed_source: str | Path, claim_file: str | Path, *,
    expected_manifest_sha256: str,
    expected_claim_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Verify claimed source bytes twice with independent manifest/claim pins."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    _pin(expected_manifest_sha256, "manifest")
    _pin(expected_claim_sha256, "provenance claim")
    root = Path(installed_source).expanduser().absolute()
    raw, claim_identity = _read_policy(claim_file)
    if not hmac.compare_digest(sha256(raw).hexdigest(), expected_claim_sha256):
        raise OriginalContentProvenanceError("independent provenance pin mismatch")
    root_fd = _root_fd(root)
    try:
        original_root = _identity(root_fd)
        before = verify_exported_package(
            root, expected_manifest_sha256=expected_manifest_sha256, authorized=True,
        )
        if (before.get("offline_gameplay_reexecuted") is not True
                or before.get("manifest_sha256") != expected_manifest_sha256
                or before.get("release_certified") is not False):
            raise OriginalContentProvenanceError("canonical playable source unqualified")
        claims = _parse(
            raw, project_id=before["project_id"],
            manifest_pin=expected_manifest_sha256,
        )
        total = 0
        original_files: list[tuple[str, tuple[int, ...]]] = []
        for path, expected, _ in claims:
            identity = _file_identity(root_fd, path)
            content = _read(root_fd, path, MAX_FILE_BYTES, owner_controlled=True)
            total += len(content)
            if total > MAX_TOTAL_BYTES or not hmac.compare_digest(
                sha256(content).hexdigest(), expected,
            ):
                raise OriginalContentProvenanceError(
                    "claimed original source bytes differ or exceed budget"
                )
            # A digest alone does not prove that the pathname still names
            # the inode whose bytes were inspected. Preserve that custody
            # through the complete canonical replay, not just this read.
            if _file_identity(root_fd, path) != identity:
                raise OriginalContentProvenanceError(
                    "claimed source inode replaced during first read"
                )
            original_files.append((path, identity))
        original_file_identities = dict(original_files)
        # Re-read every file, not only the JSON manifest. A same-byte inode
        # replacement must not pass just because its SHA-256 is unchanged.
        for path, expected, _ in claims:
            if _file_identity(root_fd, path) != original_file_identities[path]:
                raise OriginalContentProvenanceError("claimed source inode replaced")
            if not hmac.compare_digest(
                sha256(_read(root_fd, path, MAX_FILE_BYTES, owner_controlled=True)).hexdigest(),
                expected,
            ):
                raise OriginalContentProvenanceError("claimed source changed during inspection")
        after = verify_exported_package(
            root, expected_manifest_sha256=expected_manifest_sha256, authorized=True,
        )
        claim_after, claim_after_identity = _read_policy(claim_file)
        _assert_original_root(root, root_fd)
        # Canonical replay verifies bytes, but same-byte replacement of a
        # claimed source inode can occur during that replay. Reopen every
        # claimed path *after* replay, and refuse to report stable custody
        # if any original inode was replaced. The claim manifest is checked
        # independently and never grants permission to repair the source.
        for path, identity in original_files:
            if _file_identity(root_fd, path) != identity:
                raise OriginalContentProvenanceError(
                    "claimed source inode replaced during canonical replay"
                )
        if (before != after or original_root != _identity(root_fd)
                or raw != claim_after or claim_identity != claim_after_identity):
            raise OriginalContentProvenanceError(
                "provenance claim or original game changed during inspection"
            )
    finally:
        os.close(root_fd)
    return {
        "schema": RECEIPT_SCHEMA,
        "status": "original_content_claims_bound_to_replayed_source_rights_unreviewed",
        "project_id": before["project_id"],
        "manifest_sha256": expected_manifest_sha256,
        "provenance_claim_sha256": expected_claim_sha256,
        "claimed_file_count": len(claims),
        "claimed_total_bytes": total,
        "claimed_paths": [item[0] for item in claims],
        "canonical_source_replay_verified": True,
        "claimed_source_hashes_verified": True,
        "claimed_source_inodes_stable": True,
        "claims_cover_entire_game": False,
        "claims_independently_authored": False,
        "rights_review_status": "unreviewed",
        "plagiarism_cleared": False,
        "publisher_identity_certified": False,
        "rights_certified": False,
        "native_device_qualified": False,
        "package_signed": False,
        "release_certified": False,
        "read_only": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app inspect-original-provenance",
        description="Verify pinned original-content claims against replayed game source",
    )
    parser.add_argument("--installed", required=True)
    parser.add_argument("--claims", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-claim-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = inspect_original_content_provenance(
            args.installed, args.claims,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_claim_sha256=args.expected_claim_sha256,
            authorized=args.trusted_local_operator,
        )
    except (PermissionError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "schema": RECEIPT_SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


__all__ = [
    "SCHEMA", "RECEIPT_SCHEMA", "OriginalContentProvenanceError",
    "inspect_original_content_provenance", "main",
]

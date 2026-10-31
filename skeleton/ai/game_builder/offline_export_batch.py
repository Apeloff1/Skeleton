"""Offline, source-pinned verification of a complete original-game export cohort.

A batch is an independently pinned canonical JSON inventory and one immutable
package directory per project. All traversal uses directory descriptors; no
model, network, Godot runtime, or shell command is executed.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import re
import stat

from .contracts import canonical_digest
from .dual_runtime_verify import (
    DualRuntimeVerificationError,
    _canonical_bytes,
    _child_fd,
    _json,
    _read,
    _root_fd,
    verify_exported_package,
)

SCHEMA = "skeleton.game_builder.offline_export_batch.v1"
RECEIPT_SCHEMA = "skeleton.game_builder.offline_export_batch_receipt.v1"
MAX_PACKAGES = 32
MAX_INDEX_BYTES = 65_536
MAX_TOTAL_VERIFIED_BYTES = 70 * 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z")


class OfflineBatchVerificationError(ValueError):
    """Untrusted batch, incomplete package, or unsupported local platform."""


def _entry(value: object) -> tuple[str, str, str]:
    if type(value) is not dict or set(value) != {
        "project_id", "package_dir", "release_sha256",
    }:
        raise OfflineBatchVerificationError("invalid package index entry")
    project_id = value["project_id"]
    package_dir = value["package_dir"]
    pin = value["release_sha256"]
    if (type(project_id) is not str or not _ID.fullmatch(project_id)
            or type(package_dir) is not str
            or not _ID.fullmatch(package_dir)
            or package_dir in (".", "..", "batch.json")
            or type(pin) is not str or not _HEX.fullmatch(pin)):
        raise OfflineBatchVerificationError("invalid package identity or pin")
    return project_id, package_dir, pin


def verify_export_batch(
    root: str | Path, *, expected_index_sha256: str, authorized: bool,
) -> dict[str, object]:
    """Verify every package through the canonical game replay implementation.

    The index pin must be obtained independently of the untrusted batch. An
    unexpected sibling, unlisted package, symlink, hardlink, malformed JSON,
    duplicate identity, or failed gameplay replay rejects the entire batch.
    """
    if authorized is not True:
        raise PermissionError("operator authorization required for batch verification")
    if (type(expected_index_sha256) is not str
            or not _HEX.fullmatch(expected_index_sha256)):
        raise OfflineBatchVerificationError("independent index SHA-256 pin required")
    try:
        root_fd = _root_fd(root)
    except (OSError, TypeError, ValueError) as exc:
        raise OfflineBatchVerificationError("unsafe batch root") from exc
    try:
        raw = _read(root_fd, "batch.json", MAX_INDEX_BYTES)
        if sha256(raw).hexdigest() != expected_index_sha256:
            raise OfflineBatchVerificationError("batch index differs from trusted pin")
        index = _json(raw, MAX_INDEX_BYTES)
        if raw != _canonical_bytes(index):
            raise OfflineBatchVerificationError("noncanonical batch index")
        if set(index) != {"schema", "packages"} or index["schema"] != SCHEMA:
            raise OfflineBatchVerificationError("unsupported batch schema")
        rows = index["packages"]
        if type(rows) is not list or not 1 <= len(rows) <= MAX_PACKAGES:
            raise OfflineBatchVerificationError("invalid batch package count")
        entries = tuple(_entry(row) for row in rows)
        dirs = tuple(entry[1] for entry in entries)
        ids = tuple(entry[0] for entry in entries)
        if (dirs != tuple(sorted(dirs)) or len(set(dirs)) != len(dirs)
                or len(set(ids)) != len(ids)):
            raise OfflineBatchVerificationError("duplicate or unordered batch entries")
        if set(os.listdir(root_fd)) != set(dirs) | {"batch.json"}:
            raise OfflineBatchVerificationError("unlisted or missing batch entries")

        receipts: list[dict[str, object]] = []
        total_bytes = 0
        total_actions = 0
        for project_id, directory, pin in entries:
            child_fd = _child_fd(root_fd, (directory,), directory=True)
            try:
                if not stat.S_ISDIR(os.fstat(child_fd).st_mode):
                    raise OfflineBatchVerificationError("package entry is not a directory")
                receipt = verify_exported_package(
                    child_fd, expected_manifest_sha256=pin, authorized=True,
                )
            finally:
                os.close(child_fd)
            if receipt["project_id"] != project_id:
                raise OfflineBatchVerificationError("project identity differs from index")
            total_bytes += receipt["verified_bytes"]
            total_actions += receipt["replayed_actions"]
            if total_bytes > MAX_TOTAL_VERIFIED_BYTES:
                raise OfflineBatchVerificationError("batch verification byte budget exceeded")
            receipts.append({
                "project_id": project_id,
                "package_dir": directory,
                "manifest_sha256": pin,
                "world_digest": receipt["world_digest"],
                "replay_digest": receipt["replay_digest"],
                "verified_files": receipt["verified_files"],
                "verified_bytes": receipt["verified_bytes"],
                "replayed_actions": receipt["replayed_actions"],
            })
        if set(os.listdir(root_fd)) != set(dirs) | {"batch.json"}:
            raise OfflineBatchVerificationError("batch entries changed during verification")
        body = {
            "schema": RECEIPT_SCHEMA,
            "index_sha256": expected_index_sha256,
            "verified_packages": len(receipts),
            "verified_bytes": total_bytes,
            "replayed_actions": total_actions,
            "packages": receipts,
            "offline_gameplay_reexecuted": True,
            "godot_executed": False,
            "rights_certified": False,
            "release_certified": False,
        }
        return {**body, "receipt_digest": canonical_digest(body)}
    except OfflineBatchVerificationError:
        raise
    except (DualRuntimeVerificationError, OSError, UnicodeError, TypeError, ValueError) as exc:
        raise OfflineBatchVerificationError("batch verification rejected") from exc
    finally:
        os.close(root_fd)


__all__ = [
    "OfflineBatchVerificationError", "verify_export_batch",
    "SCHEMA", "RECEIPT_SCHEMA",
]

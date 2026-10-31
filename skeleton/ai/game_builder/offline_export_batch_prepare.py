"""Safely author a pinned offline game cohort index from verified real exports.

Only a trusted local operator can prepare an index. The command verifies each
package through the canonical replay engine BEFORE writing, then publishes a
canonical index without clobbering an existing file. The printed pin must be
transferred independently to the future verifying operator.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import secrets
import stat
from typing import Mapping, Sequence

from .contracts import canonical_digest
from .dual_runtime_verify import (
    DualRuntimeVerificationError, _bounded_names, _canonical_bytes, _child_fd, _root_fd,
    verify_exported_package,
)
from .offline_export_batch import (
    MAX_INDEX_BYTES, MAX_PACKAGES, SCHEMA,
    OfflineBatchVerificationError, _entry,
)

PREPARE_RECEIPT_SCHEMA = "skeleton.game_builder.offline_export_batch_prepare.v1"


def prepare_export_batch(
    root: str | Path, *, entries: Sequence[Mapping[str, str]],
    authorized: bool,
) -> dict[str, object]:
    """Verify and atomically publish a never-overwritten batch.json.

    Publication uses a same-directory private temporary file, fsync and
    hardlink-based no-clobber creation. A crash before publication leaves only
    an invalid temporary artifact, not a trusted batch pin.
    """
    if authorized is not True:
        raise PermissionError("operator authorization required for batch preparation")
    if type(entries) not in (tuple, list) or not 1 <= len(entries) <= MAX_PACKAGES:
        raise OfflineBatchVerificationError("invalid batch preparation entry count")
    parsed = tuple(_entry(item) for item in entries)
    directories = tuple(row[1] for row in parsed)
    project_ids = tuple(row[0] for row in parsed)
    if len(set(directories)) != len(directories) or len(set(project_ids)) != len(project_ids):
        raise OfflineBatchVerificationError("duplicate batch identity")
    ordered = tuple(sorted(parsed, key=lambda item: item[1]))
    manifest = {
        "schema": SCHEMA,
        "packages": [
            {"project_id": project_id, "package_dir": directory,
             "release_sha256": pin}
            for project_id, directory, pin in ordered
        ],
    }
    data = _canonical_bytes(manifest)
    if len(data) > MAX_INDEX_BYTES:
        raise OfflineBatchVerificationError("batch index exceeds byte bound")
    try:
        root_fd = _root_fd(root)
    except (OSError, TypeError, ValueError) as exc:
        raise OfflineBatchVerificationError("unsafe batch root") from exc
    try:
        info = os.fstat(root_fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022
                or info.st_uid != os.geteuid()):
            raise OfflineBatchVerificationError("batch root must be owner-private for writes")
        if set(_bounded_names(root_fd, MAX_PACKAGES)) != set(directories):
            raise OfflineBatchVerificationError("batch root has unlisted or missing entries")
        replay_digests: list[str] = []
        for project_id, directory, pin in ordered:
            child_fd = _child_fd(root_fd, (directory,), directory=True)
            try:
                result = verify_exported_package(
                    child_fd, expected_manifest_sha256=pin, authorized=True,
                )
            finally:
                os.close(child_fd)
            if result["project_id"] != project_id:
                raise OfflineBatchVerificationError("package identity differs from entry")
            replay_digests.append(result["replay_digest"])

        temporary = ".batch-" + secrets.token_hex(16)
        temp_fd = -1
        published = False
        temp_identity: tuple[int, int] | None = None
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            temp_fd = os.open(temporary, flags, 0o600, dir_fd=root_fd)
            identity = os.fstat(temp_fd)
            temp_identity = (identity.st_dev, identity.st_ino)
            position = 0
            while position < len(data):
                written = os.write(temp_fd, data[position:])
                if written <= 0:
                    raise OfflineBatchVerificationError("batch index write made no progress")
                position += written
            os.fsync(temp_fd)
            os.close(temp_fd)
            temp_fd = -1
            # link() rejects an existing batch.json, unlike rename() which may
            # silently overwrite a concurrent publisher's index.
            os.link(
                temporary, "batch.json",
                src_dir_fd=root_fd, dst_dir_fd=root_fd,
                follow_symlinks=False,
            )
            published = True
            linked = os.stat("batch.json", dir_fd=root_fd, follow_symlinks=False)
            if (not stat.S_ISREG(linked.st_mode)
                    or (linked.st_dev, linked.st_ino) != temp_identity
                    or linked.st_size != len(data)):
                raise OfflineBatchVerificationError(
                    "published index identity differs from verified temporary file"
                )
            os.fsync(root_fd)
        except BaseException:
            if temp_fd >= 0:
                os.close(temp_fd)
            if published and temp_identity is not None:
                try:
                    current = os.stat(
                        "batch.json", dir_fd=root_fd, follow_symlinks=False,
                    )
                    if (current.st_dev, current.st_ino) == temp_identity:
                        os.unlink("batch.json", dir_fd=root_fd)
                except OSError:
                    pass
            raise
        finally:
            try:
                os.unlink(temporary, dir_fd=root_fd)
            except FileNotFoundError:
                pass
        os.fsync(root_fd)
        body = {
            "schema": PREPARE_RECEIPT_SCHEMA,
            "index_sha256": sha256(data).hexdigest(),
            "prepared_packages": len(ordered),
            "replay_proof_digest": canonical_digest(replay_digests),
            "operator_must_transfer_pin_independently": True,
            "godot_executed": False,
            "rights_certified": False,
            "release_certified": False,
        }
        return {**body, "receipt_digest": canonical_digest(body)}
    except OfflineBatchVerificationError:
        raise
    except (DualRuntimeVerificationError, OSError, TypeError, ValueError) as exc:
        raise OfflineBatchVerificationError("batch preparation rejected") from exc
    finally:
        os.close(root_fd)


__all__ = ["prepare_export_batch", "PREPARE_RECEIPT_SCHEMA"]

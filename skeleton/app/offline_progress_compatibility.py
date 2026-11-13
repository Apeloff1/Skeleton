"""Read-only replay binding of private progress to an independently pinned ZIP.

This gate runs before a destination is reserved. It never extracts or executes
archive members, writes a save, or claims signed/device-qualified delivery.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import hmac
import os
import stat
from pathlib import Path
import re
from zipfile import ZipFile, BadZipFile, LargeZipFile

from skeleton.ai.game_builder.dual_runtime_verify import (
    _MAX_BYTES, _MAX_MANIFEST, _assert_original_root, _json, _world,
)
from skeleton.ai.game_builder.playable_simulation import (
    MAX_SERIALIZED_REPLAY_BYTES, deserialize_replay,
)
from skeleton.app.offline_delivery_archive import (
    _parent as _archive_parent, _read_private_archive,
    inspect_offline_game_archive,
)

SCHEMA = "skeleton.app.offline_archive_save_compatibility.v1"
_HEX = re.compile(r"[0-9a-f]{64}\Z")


class OfflineArchiveSaveCompatibilityError(ValueError):
    """A pinned archive and canonical private save cannot be admitted together."""


def _pin(value: object, name: str) -> str:
    if type(value) is not str or not _HEX.fullmatch(value):
        raise OfflineArchiveSaveCompatibilityError(
            "independent " + name + " SHA-256 pin required"
        )
    return value


def _archive_identity(path: str | Path) -> tuple[int, ...]:
    """Pin path, owner, and inode metadata across the entire replay admission."""
    target, parent_fd = _archive_parent(path)
    try:
        info = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or info.st_mode & 0o077):
            raise OfflineArchiveSaveCompatibilityError(
                "archive path is not a private regular inode"
            )
        _assert_original_root(target.parent, parent_fd)
        return (
            info.st_dev, info.st_ino, info.st_size, info.st_mode,
            info.st_nlink, info.st_uid, info.st_mtime_ns, info.st_ctime_ns,
        )
    finally:
        os.close(parent_fd)


def verify_archived_progress_binding(
    archive: str | Path, save_bytes: bytes, *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    expected_save_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Replay the private save against a verified world without installation.

    Three pins must be supplied independently of the archive and save.
    The canonical ZIP inspection verifies the entire source inventory before
    constructing a typed world from its pinned release and Godot world JSON.
    The archive is read again through a private nofollow descriptor and
    independently checked after replay. Preflight is not a reservation.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    archive_pin = _pin(expected_archive_sha256, "archive")
    manifest_pin = _pin(expected_manifest_sha256, "manifest")
    save_pin = _pin(expected_save_sha256, "save")
    if (type(save_bytes) is not bytes
            or not 0 < len(save_bytes) <= MAX_SERIALIZED_REPLAY_BYTES):
        raise OfflineArchiveSaveCompatibilityError("invalid bounded save bytes")
    if not hmac.compare_digest(sha256(save_bytes).hexdigest(), save_pin):
        raise OfflineArchiveSaveCompatibilityError("save differs from independent pin")
    identity_before = _archive_identity(archive)
    before = inspect_offline_game_archive(
        archive, expected_archive_sha256=archive_pin,
        expected_manifest_sha256=manifest_pin, authorized=True,
    )
    raw = _read_private_archive(archive)
    if not hmac.compare_digest(sha256(raw).hexdigest(), archive_pin):
        raise OfflineArchiveSaveCompatibilityError(
            "archive changed after inventory inspection"
        )
    try:
        with ZipFile(BytesIO(raw), "r", allowZip64=False) as bundle:
            release_bytes = bundle.read("release.json")
            world_bytes = bundle.read("godot/world.json")
        if (len(release_bytes) > _MAX_MANIFEST
                or len(world_bytes) > _MAX_BYTES
                or not hmac.compare_digest(
                    sha256(release_bytes).hexdigest(), manifest_pin
                )):
            raise OfflineArchiveSaveCompatibilityError(
                "archived release differs from independent pin"
            )
        manifest = _json(release_bytes, _MAX_MANIFEST)
        world = _world(_json(world_bytes, _MAX_BYTES), manifest)
        replay = deserialize_replay(world, save_bytes, authorized=True)
    except (BadZipFile, LargeZipFile, KeyError, TypeError,
            ValueError, UnicodeError, RuntimeError) as exc:
        if isinstance(exc, OfflineArchiveSaveCompatibilityError):
            raise
        raise OfflineArchiveSaveCompatibilityError(
            "private progress incompatible with archived original world"
        ) from exc
    after = inspect_offline_game_archive(
        archive, expected_archive_sha256=archive_pin,
        expected_manifest_sha256=manifest_pin, authorized=True,
    )
    identity_after = _archive_identity(archive)
    if (identity_before != identity_after or before != after
            or after.get("archive_integrity_verified") is not True):
        raise OfflineArchiveSaveCompatibilityError(
            "source archive changed during compatibility replay"
        )
    return {
        "schema": SCHEMA,
        "status": "pinned_archived_progress_replayed_read_only_release_blocked",
        "project_id": world.intent.project_id,
        "archive_sha256": archive_pin,
        "manifest_sha256": manifest_pin,
        "save_sha256": save_pin,
        "world_digest": world.digest,
        "replay_digest": replay.digest,
        "action_count": len(replay.action_receipts),
        "final_state": replay.final_state.to_payload(),
        "archive_integrity_verified": True,
        "save_world_binding_verified": True,
        "private_save_replayed": True,
        "read_only": True,
        "destination_reserved": False,
        "source_installation_verified": False,
        "model_inference_observed": False,
        "native_godot_executed": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


__all__ = [
    "SCHEMA", "OfflineArchiveSaveCompatibilityError",
    "verify_archived_progress_binding",
]

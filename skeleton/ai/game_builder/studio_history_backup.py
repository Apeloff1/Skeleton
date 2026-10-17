"""Create-only, source-locked offline snapshots of Jeeves original-game run history.

Copies ONLY validated qualification_history.json and its sealed run segments.
Never exports ROM bytes, media, authored assets, prompts or model weights.
Backups are not native execution or long-duration qualification evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import shutil
import tempfile

from .studio_campaign_lock import campaign_lock
from .studio_execution_history import _read_history

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
MAX_FILE_BYTES = 256_000


class StudioHistoryBackupError(ValueError):
    """Backup file, identity, manifest or source chain changed."""


def _private(root: Path) -> Path:
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise StudioHistoryBackupError("existing absolute private output required")
    if os.name == "posix":
        info = root.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise StudioHistoryBackupError("history snapshot output must be mode 0700")
    return root


def _checked_bytes(path: Path, *, limit: int = MAX_FILE_BYTES) -> bytes:
    if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
        raise StudioHistoryBackupError("expected bounded regular history file")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= limit:
        raise StudioHistoryBackupError("history file exceeds snapshot limits")
    content = path.read_bytes()
    after = path.stat()
    if (len(content) != before.st_size or before.st_ino != after.st_ino
            or before.st_mtime_ns != after.st_mtime_ns):
        raise StudioHistoryBackupError("history file changed during intake")
    return content


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def verify_studio_history_snapshot(destination: Path, *, name: str,
                                   identity: str) -> dict:
    destination = _private(Path(destination))
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise StudioHistoryBackupError("invalid backup name")
    snapshot = destination / name
    if snapshot.is_symlink() or not snapshot.is_dir():
        raise StudioHistoryBackupError("snapshot is unavailable")
    try:
        manifest = json.loads(_checked_bytes(
            snapshot / "snapshot_manifest.json", limit=131_072))
    except (ValueError, UnicodeError) as exc:
        raise StudioHistoryBackupError("invalid history snapshot manifest") from exc
    if (type(manifest) is not dict or set(manifest) != {
            "schema", "campaign_identity", "files", "entry_count"}
            or manifest["schema"] != "skeleton.game_builder.history_snapshot.v1"
            or manifest["campaign_identity"] != identity
            or type(manifest["files"]) is not dict
            or not 1 <= len(manifest["files"]) <= 513):
        raise StudioHistoryBackupError("snapshot schema and identity mismatch")
    expected = {"qualification_history.json"}
    expected.update(
        f"qualification_history_segments/segment-{number:05d}.json"
        for number in range(1, len(manifest["files"]))
    )
    if set(manifest["files"]) != expected:
        raise StudioHistoryBackupError("snapshot missing a segment or contains extra paths")
    for path, digest in manifest["files"].items():
        if (type(digest) is not str or len(digest) != 64
                or _hash(_checked_bytes(snapshot / path)) != digest):
            raise StudioHistoryBackupError("snapshot content differs from manifest")
    try:
        checked = _read_history(snapshot, identity)
    except (ValueError, OSError) as exc:
        raise StudioHistoryBackupError("offline journal chain cannot be validated") from exc
    total = checked["_archive_stats"]["archive_entry_count"] + len(checked["entries"])
    if type(manifest["entry_count"]) is not int or manifest["entry_count"] != total:
        raise StudioHistoryBackupError("snapshot receipt count differs")
    return {
        "verified": True, "name": name, "campaign_identity": identity,
        "files": len(expected), "historical_runs": total,
        "sealed_segments": checked["_archive_stats"]["segments_used"],
        "native_runtime_replayed": False, "backup_restored": False,
        "release_or_model_training_qualified": False,
    }


def snapshot_studio_history(source: Path, destination: Path, *,
                            name: str, identity: str) -> dict:
    """Lock against concurrent campaign writes and seal an exclusive offline copy."""
    source, destination = Path(source), _private(Path(destination))
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise StudioHistoryBackupError("invalid snapshot name")
    target = destination / name
    if target.exists() or target.is_symlink():
        raise StudioHistoryBackupError("snapshot names cannot be reused")
    with campaign_lock(source):
        checked = _read_history(source, identity)
        if not (source / "qualification_history.json").is_file():
            raise StudioHistoryBackupError("no persisted qualification runs")
        relative_paths = ["qualification_history.json"] + [
            "qualification_history_segments/" + segment["file"]
            for segment in checked.get("segments", [])
        ]
        target.mkdir(mode=0o700)
        files = {}
        for relative in relative_paths:
            raw = _checked_bytes(source / relative)
            output = target / relative
            output.parent.mkdir(mode=0o700, exist_ok=True)
            fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            files[relative] = _hash(raw)
        manifest = {
            "schema": "skeleton.game_builder.history_snapshot.v1",
            "campaign_identity": identity, "files": files,
            "entry_count": checked["_archive_stats"]["archive_entry_count"] + len(checked["entries"]),
        }
        raw = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
        fd = os.open(target / "snapshot_manifest.json",
                     os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    return verify_studio_history_snapshot(destination, name=name, identity=identity)


def restore_studio_history(snapshot_root: Path, destination: Path, *,
                           name: str, identity: str) -> dict:
    """Verify, restore and atomically publish a NEW game run journal directory.

    Never writes over a live campaign, starts a native runtime, silently
    authorizes a lease, or marks incomplete runs as qualified. A private
    staging directory is destroyed on failure; the destination is exposed
    only after independent archive-chain validation succeeds.
    """
    snapshot_root = _private(Path(snapshot_root))
    destination = Path(destination)
    if not destination.is_absolute() or not destination.name:
        raise StudioHistoryBackupError("restore destination must be an absolute new directory")
    parent = _private(destination.parent)
    source = snapshot_root / name
    evidence = verify_studio_history_snapshot(snapshot_root, name=name, identity=identity)
    with campaign_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise StudioHistoryBackupError("restoration cannot replace an existing campaign")
        stage = Path(tempfile.mkdtemp(prefix=".studio-history-restore-", dir=parent))
        try:
            manifest = json.loads(_checked_bytes(
                source / "snapshot_manifest.json", limit=131_072,
            ))
            for relative, digest in sorted(manifest["files"].items()):
                original = source / relative
                raw = _checked_bytes(original)
                if _hash(raw) != digest:
                    raise StudioHistoryBackupError("snapshot file changed during restoration")
                published = stage / relative
                published.parent.mkdir(mode=0o700, exist_ok=True)
                fd = os.open(published, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
            try:
                restored = _read_history(stage, identity)
            except (ValueError, OSError) as exc:
                raise StudioHistoryBackupError("restored journal chain is inconsistent") from exc
            count = restored["_archive_stats"]["archive_entry_count"] + len(restored["entries"])
            if count != evidence["historical_runs"]:
                raise StudioHistoryBackupError("restored journal entry count differs")
            # The sealed source must still agree immediately before publication.
            if verify_studio_history_snapshot(
                snapshot_root, name=name, identity=identity,
            ) != evidence:
                raise StudioHistoryBackupError("snapshot changed during restoration")
            if destination.exists() or destination.is_symlink():
                raise StudioHistoryBackupError("restore target appeared during copy")
            os.rename(stage, destination)
            if os.name == "posix":
                try:
                    fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                except OSError:
                    # The restored files are individually fsynced. Lack of
                    # directory fsync support must not forge release status.
                    pass
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return {
        **evidence,
        "backup_restored": True,
        "restored_to_new_directory": True,
        "campaign_started_or_resumed": False,
        "operator_reauthorization_required": True,
        "restored_history_revalidated": True,
    }

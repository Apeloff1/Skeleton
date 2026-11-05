"""Non-destructive, fail-closed custody backup for legacy Chroma /data.

The pinned image persists under /data, but older Compose mounts its volume at
/chroma/chroma. This tool NEVER starts, stops, removes, recreates or migrates a
container. An operator must stop writers and the old container first.
A backup is evidence for a later, separately authorized migration.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

SCHEMA = "skeleton.chroma.legacy-backup.v1"
CONTAINER = "tutolage-chroma"
MAX_FILES = 100_000
MAX_BYTES = 100 * 1024 ** 3
MAX_MANIFEST_BYTES = 32 * 1024 ** 2


class BackupRejected(RuntimeError):
    """The existing Chroma container could not be safely backed up."""


def _docker(*args: str) -> str:
    try:
        result = subprocess.run(
            ["docker", *args], check=True, text=True, capture_output=True,
            timeout=3600,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        # Docker errors can include private environment or container paths.
        raise BackupRejected("Docker custody command failed: " + args[0]) from exc
    return result.stdout


def _inspect(container: str) -> dict:
    try:
        objects = json.loads(_docker("inspect", container))
    except (ValueError, TypeError) as exc:
        raise BackupRejected("Docker returned invalid container metadata") from exc
    if not isinstance(objects, list) or len(objects) != 1 or not isinstance(objects[0], dict):
        raise BackupRejected("expected one existing Chroma container")
    info = objects[0]
    state = info.get("State") or {}
    if (info.get("Name") != "/" + container
            or state.get("Status") != "exited"
            or state.get("Running") is not False
            or state.get("Restarting") is not False
            or not isinstance(state.get("StartedAt"), str)
            or not isinstance(state.get("FinishedAt"), str)
            or type(info.get("RestartCount")) is not int):
        raise BackupRejected("stop the exact Chroma container and all writers before backup")
    mounts = info.get("Mounts")
    if not isinstance(mounts, list) or any(not isinstance(m, dict) or not isinstance(m.get("Destination"), str) for m in mounts):
        raise BackupRejected("unexpected Chroma persistence mounts; do not guess data authority")
    legacy = [m for m in mounts if m.get("Destination") == "/chroma/chroma"]
    if (len(legacy) != 1 or legacy[0].get("Type") != "volume"
            or not isinstance(legacy[0].get("Name"), str)
            or not legacy[0]["Name"] or any(
                m["Destination"] == "/data" or m["Destination"].startswith("/data/")
                or m["Destination"].startswith("/chroma/chroma/")
                for m in mounts)):
        raise BackupRejected("unexpected Chroma persistence mounts; do not guess data authority")
    if not isinstance(info.get("Id"), str) or not info["Id"]:
        raise BackupRejected("missing immutable Chroma container identity")
    return {
        "id": info["Id"],
        "image": str((info.get("Config") or {}).get("Image", "")),
        "volume": legacy[0]["Name"],
        "mounts": mounts,
        # A stop/start/stop cycle between inspections otherwise looks identical
        # and could make the two copies represent different database states.
        "started_at": state["StartedAt"],
        "finished_at": state["FinishedAt"],
        "restart_count": info["RestartCount"],
    }


def _publish_no_replace(source: Path, destination: Path) -> None:
    """Atomically publish a directory without replacing a concurrent target."""
    if os.name == "nt":
        # Windows rename refuses an existing destination, including a directory.
        try:
            os.rename(source, destination)
        except FileExistsError as exc:
            raise BackupRejected("backup destination already exists; never overwrite evidence") from exc
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith("linux"):
        rename = getattr(libc, "renameat2", None)
        if rename is None:
            raise BackupRejected("atomic no-replace publication is unavailable on this platform")
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    elif sys.platform == "darwin":
        rename = getattr(libc, "renamex_np", None)
        if rename is None:
            raise BackupRejected("atomic no-replace publication is unavailable on this platform")
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(os.fsencode(source), os.fsencode(destination), 4)
    else:
        raise BackupRejected("atomic no-replace publication is unavailable on this platform")
    if result != 0:
        error = ctypes.get_errno()
        if error in (errno.EEXIST, errno.ENOTEMPTY):
            raise BackupRejected("backup destination already exists; never overwrite evidence")
        raise BackupRejected("atomic no-replace backup publication failed")


def _manifest_files(root: Path, *, exclude_root_manifest: bool = False) -> list[dict]:
    entries: list[dict] = []
    count = total = 0
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise BackupRejected("backed-up Chroma contains a link or special file")
        if stat.S_ISDIR(mode):
            continue
        if exclude_root_manifest and path == root / "manifest.json":
            continue
        count += 1
        if count > MAX_FILES:
            raise BackupRejected("Chroma backup exceeds file admission budget")
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(chunk)
                total += len(chunk)
                if total > MAX_BYTES:
                    raise BackupRejected("Chroma backup exceeds byte admission budget")
                digest.update(chunk)
        entries.append({
            "path": path.relative_to(root).as_posix(),
            "bytes": size,
            "sha256": digest.hexdigest(),
        })
    return entries


def backup_legacy_chroma(output: Path, *, container: str = CONTAINER) -> dict:
    """Copy both legacy stores with no destructive Docker operation.

    The output must be a previously nonexistent path; on any failure no
    completed backup is published, and the original container remains intact.
    """
    requested = Path(output).expanduser().absolute()
    if any(path.is_symlink() for path in (requested, *requested.parents)):
        raise BackupRejected("backup destination and its parents cannot be symlinks")
    output = requested.resolve(strict=False)
    repository_root = Path(__file__).resolve().parents[1]
    if output == repository_root or repository_root in output.parents:
        raise BackupRejected("private Chroma backups must be outside the repository")
    if output.exists() or output.is_symlink():
        raise BackupRejected("backup destination already exists; never overwrite evidence")
    parent = output.parent
    if not parent.is_dir() or parent.is_symlink():
        raise BackupRejected("backup parent must be an existing real directory")
    if not container or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in container):
        raise BackupRejected("container name is not canonical")
    before = _inspect(container)
    with tempfile.TemporaryDirectory(prefix=".chroma-custody-", dir=parent) as tmp:
        staging = Path(tmp)
        staging.chmod(0o700)
        for component, source in (
            ("container-data", "/data/."),
            ("legacy-volume", "/chroma/chroma/."),
        ):
            destination = staging / component
            destination.mkdir(mode=0o700)
            _docker("cp", container + ":" + source, str(destination))
        after = _inspect(container)
        if before != after:
            raise BackupRejected("Chroma container identity or mounts changed during backup")
        files = _manifest_files(staging)
        if not files:
            raise BackupRejected("Chroma backup contained no files")
        manifest = {
            "schema": SCHEMA,
            "source_container_id": before["id"],
            "source_image": before["image"],
            "legacy_volume": before["volume"],
            "source_was_stopped": True,
            "files": files,
            "migration_complete": False,
            "release_accepted": False,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8",
        )
        # Rename only after both copies, the second inspect and content hashes.
        # Keep evidence private; Docker cp may restore broad file permissions.
        _publish_no_replace(staging, output)
        output.chmod(0o700)
        return manifest


def verify_backup(backup: Path) -> dict:
    """Recheck a custody backup without modifying it or contacting Docker.

    Hash matching detects changes relative to the supplied manifest; the
    manifest is not a signature and this does not establish database integrity,
    source authority or authorization to restore.
    """
    root = Path(backup).expanduser().absolute()
    if any(path.is_symlink() for path in (root, *root.parents)) or not root.is_dir():
        raise BackupRejected("backup must be an existing directory without symlink parents")
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise BackupRejected("backup manifest is missing or unsafe")
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise BackupRejected("backup manifest exceeds admission budget")
    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise BackupRejected("backup manifest contains duplicate keys")
            value[key] = item
        return value
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (OSError, ValueError, UnicodeError) as exc:
        raise BackupRejected("backup manifest cannot be read") from exc
    if (not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA
        or manifest.get("source_was_stopped") is not True
        or manifest.get("migration_complete") is not False
        or manifest.get("release_accepted") is not False
        or not isinstance(manifest.get("files"), list)
        or not (root / "container-data").is_dir() or not (root / "legacy-volume").is_dir()):
        raise BackupRejected("backup manifest or store directories are invalid")
    expected = manifest["files"]
    if not expected or len(expected) > MAX_FILES:
        raise BackupRejected("backup manifest file count is invalid")
    for entry in expected:
        if (not isinstance(entry, dict) or set(entry) != {"path", "bytes", "sha256"}
            or not isinstance(entry["path"], str) or not isinstance(entry["sha256"], str)
            or type(entry["bytes"]) is not int or entry["bytes"] < 0
            or len(entry["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in entry["sha256"])):
            raise BackupRejected("backup manifest file entry is invalid")
    actual = _manifest_files(root, exclude_root_manifest=True)
    if actual != expected:
        raise BackupRejected("backup contents do not match the recorded manifest")
    return {"schema": SCHEMA, "files": len(actual), "matches_manifest": True,
            "database_integrity_verified": False, "migration_complete": False,
            "release_accepted": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path, help="NEW private directory outside the repository")
    mode.add_argument("--verify", type=Path, help="recheck a completed custody backup without Docker")
    parser.add_argument("--container", default=CONTAINER)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.verify is not None:
            print(json.dumps(verify_backup(args.verify), sort_keys=True))
            return 0
        result = backup_legacy_chroma(args.output, container=args.container)
    except BackupRejected as exc:
        parser.exit(2, "Chroma backup rejected: " + str(exc) + "\n")
    print(json.dumps({
        "backup": str(args.output.expanduser().absolute()),
        "files": len(result["files"]),
        "legacy_volume": result["legacy_volume"],
        "migration_complete": False,
        "release_accepted": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

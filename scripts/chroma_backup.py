"""Non-destructive, fail-closed custody backup for legacy Chroma /data.

The pinned image persists under /data, but older Compose mounts its volume at
/chroma/chroma. This tool NEVER starts, stops, removes, recreates or migrates a
container. An operator must stop writers and the old container first.
A backup is evidence for a later, separately authorized migration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

SCHEMA = "skeleton.chroma.legacy-backup.v1"
CONTAINER = "tutolage-chroma"
MAX_FILES = 100_000
MAX_BYTES = 100 * 1024 ** 3


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
            or state.get("Restarting") is not False):
        raise BackupRejected("stop the exact Chroma container and all writers before backup")
    mounts = info.get("Mounts") or []
    legacy = [m for m in mounts if m.get("Destination") == "/chroma/chroma"]
    if (len(legacy) != 1 or legacy[0].get("Type") != "volume"
            or not isinstance(legacy[0].get("Name"), str)
            or not legacy[0]["Name"] or any(m.get("Destination") == "/data" for m in mounts)):
        raise BackupRejected("unexpected Chroma persistence mounts; do not guess data authority")
    if not isinstance(info.get("Id"), str) or not info["Id"]:
        raise BackupRejected("missing immutable Chroma container identity")
    return {
        "id": info["Id"],
        "image": str((info.get("Config") or {}).get("Image", "")),
        "volume": legacy[0]["Name"],
        "mounts": mounts,
    }


def _manifest_files(root: Path) -> list[dict]:
    entries: list[dict] = []
    count = total = 0
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise BackupRejected("backed-up Chroma contains a link or special file")
        if stat.S_ISDIR(mode):
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
    output = Path(output).expanduser().absolute()
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
        staging.rename(output)
        output.chmod(0o700)
        return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="NEW private directory outside the repository")
    parser.add_argument("--container", default=CONTAINER)
    args = parser.parse_args()
    os.umask(0o077)
    try:
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

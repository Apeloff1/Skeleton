"""Read-only Docker storage admission for first-install credential generation.

The canonical Compose stack uses fixed container names and five named volumes.
An absent .env is not evidence that those volumes are absent. Observe the
selected daemon before allowing a new persistent credential identity. Never
inspect container Config.Env, database content, arbitrary labels or mount paths.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Mapping

VOLUME_ROLES = ("mongo_data", "mongo_config", "skeleton_data", "backend_data", "chroma_data")
CONTAINER_ROLES = ("mongo", "skeleton", "backend", "frontend", "chroma")
DURABLE_KEYS = frozenset({
    "MONGO_INITDB_ROOT_PASSWORD", "MONGO_INITDB_ROOT_USERNAME",
    "GAMEFORGE_JWT_SECRET", "GF_SEAL_SECRET", "GF_KEYHOLDER_SEED", "SKELETON_MASTER_SECRET",
})
_MAX_BYTES = 1024 * 1024
_MAX_ROWS = 8192
_NAME = re.compile(rb"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}\Z")


class StorageCustodyDenied(ValueError):
    """The selected daemon or existing storage has not admitted new identity."""


@dataclass(frozen=True, slots=True)
class StorageObservation:
    observed: bool
    volume_roles: tuple[str, ...] = ()
    container_roles: tuple[str, ...] = ()

    @property
    def new_credentials_permitted(self):
        return self.observed is True and not self.volume_roles and not self.container_roles

    def to_dict(self):
        return {
            "schema": "skeleton.app.storage_custody.v1",
            "observed": self.observed,
            "volume_roles": list(self.volume_roles),
            "container_roles": list(self.container_roles),
            "new_credentials_permitted": self.new_credentials_permitted,
            "database_authenticated": False,
            "backup_verified": False,
            "storage_modified": False,
            "scope": "Selected Docker daemon inventory only; not database or backup qualification.",
        }


def _names(root, runner, args, environ):
    # Disk-backed capture and a bounded read: no arbitrary daemon text or
    # resource identifiers enter the report. The caller's environment is
    # preserved to observe its actual selected Docker context.
    with tempfile.TemporaryFile() as output:
        done = runner(["docker", *args], cwd=root, env=dict(environ),
                      check=False, stdin=subprocess.DEVNULL, stdout=output,
                      stderr=subprocess.DEVNULL, text=False, timeout=15.0)
        status = getattr(done, "returncode", None)
        if type(status) is not int or status != 0:
            raise StorageCustodyDenied("Docker storage observation unavailable")
        output.seek(0)
        raw = output.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES or (raw and not raw.endswith(b"\n")):
        raise StorageCustodyDenied("Docker storage observation incomplete")
    rows = raw.splitlines()
    if (len(rows) > _MAX_ROWS or len(set(rows)) != len(rows)
            or any(_NAME.fullmatch(row) is None for row in rows)):
        raise StorageCustodyDenied("Docker storage observation invalid")
    return frozenset(row.decode("ascii") for row in rows)


def observe_storage(root: Path, *, runner=subprocess.run, environ: Mapping[str,str] | None=None):
    root = Path(root).resolve()
    captured = dict(os.environ if environ is None else environ)
    try:
        names = _names(root, runner, ["volume","ls","--format","{{.Name}}"], captured)
        containers = _names(root, runner, ["ps","--all","--format","{{.Names}}"], captured)
        roles = set()
        # Include legacy or manually initialized volumes whose canonical
        # suffix remains but whose original Compose labels are absent.
        for role in VOLUME_ROLES:
            if any(name == role or name.endswith("_" + role) for name in names):
                roles.add(role)
        # Also include custom-name Compose volumes carrying a canonical role.
        for role in VOLUME_ROLES:
            labeled = _names(root, runner, ["volume","ls","--filter",
                             "label=com.docker.compose.volume=" + role,
                             "--format","{{.Name}}"], captured)
            if not labeled.issubset(names):
                # Docker custody changed between inventory passes.
                return StorageObservation(False)
            if labeled:
                roles.add(role)
        # Refuse a changing inventory; never reinterpret a removed volume or
        # an appearing container as proof that the daemon is a clean install.
        if (_names(root, runner, ["volume","ls","--format","{{.Name}}"], captured) != names
                or _names(root, runner, ["ps","--all","--format","{{.Names}}"], captured) != containers):
            return StorageObservation(False)
        existing = tuple(role for role in CONTAINER_ROLES if "tutolage-" + role in containers)
        return StorageObservation(True, tuple(role for role in VOLUME_ROLES if role in roles), existing)
    except (StorageCustodyDenied, OSError, subprocess.SubprocessError, ValueError, UnicodeError):
        return StorageObservation(False)


def require_new_storage_identity(root: Path, *, runner=subprocess.run, environ=None):
    observation = observe_storage(root, runner=runner, environ=environ)
    if not observation.observed:
        raise StorageCustodyDenied(
            "Docker storage inventory unverified; restore the original private .env or verify the selected daemon"
        )
    if not observation.new_credentials_permitted:
        raise StorageCustodyDenied(
            "Existing application storage or containers detected; restore original persistent credentials before setup"
        )
    return observation


def main(argv, *, root: Path):
    parser = argparse.ArgumentParser(prog="storage-custody",
        description="Read-only inventory of canonical storage on the selected Docker daemon.")
    parser.parse_args(argv)
    value = observe_storage(root)
    print(json.dumps(value.to_dict(), sort_keys=True))
    return 0 if value.observed else 1

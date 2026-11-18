"""Read-only, fail-closed Docker application-state volume recovery preflight.

This tool *never* claims that Docker volumes are an atomic Mongo/SQLite/Chroma
backup. It verifies the effective canonical Compose stateful volume identities,
their physical daemon metadata and running attachments without exposing Mongo
credentials, image environment or the host's private Docker mountpoints.

Not a migration, snapshot, image export, volume copy, restore or stop operation.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from scripts import local_ai_docker as host

_SCHEMA = "skeleton.local-ai.docker-application-recovery-preflight.v1"
_VOLUME_ROLES = {
    "skeleton_data": ("skeleton", "/app/data"),
    "backend_data": ("backend", "/app/data"),
    "mongo_data": ("mongo", "/data/db"),
    "mongo_config": ("mongo", "/data/configdb"),
    "chroma_data": ("chroma", "/chroma/chroma"),
}
_REQUIRED = frozenset({"skeleton_data", "backend_data", "mongo_data", "mongo_config"})
_LABEL_PROJECT = "com.docker.compose.project"
_LABEL_VOLUME = "com.docker.compose.volume"
_ID = re.compile(r"[a-f0-9]{12,64}\Z")
_PROJECT = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}\Z")
_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,255}\Z")


def _json(raw: object, *, limit: int) -> object:
    if not isinstance(raw, str) or len(raw) > limit:
        raise host.LocalDockerError("Docker recovery metadata exceeds bounded response")
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        raise host.LocalDockerError("Docker recovery metadata is not JSON") from None


def _expected_volumes(topology: Mapping[str, Any]) -> dict[str, str]:
    """Derive actual Compose volume names, never guess project prefixes."""
    name = topology.get("name")
    if not isinstance(name, str) or not _PROJECT.fullmatch(name):
        raise host.LocalDockerError("canonical Compose project identity is invalid")
    declared = topology.get("volumes")
    services = topology.get("services")
    if not isinstance(declared, dict) or not isinstance(services, dict):
        raise host.LocalDockerError("canonical Compose persistent volumes unavailable")
    if not _REQUIRED.issubset(declared) or set(declared) - set(_VOLUME_ROLES):
        raise host.LocalDockerError("canonical Compose persistent volume inventory differs")
    observed: dict[str, str] = {}
    for logical, (service, target) in _VOLUME_ROLES.items():
        if logical not in declared:
            if logical in _REQUIRED:
                raise host.LocalDockerError("mandatory application state volume missing")
            continue
        spec = declared[logical]
        if not isinstance(spec, dict) or not isinstance(spec.get("name"), str):
            raise host.LocalDockerError("persistent volume physical name missing")
        physical = spec["name"]
        if not _NAME.fullmatch(physical) or physical in observed.values():
            raise host.LocalDockerError("application state volume identities overlap")
        if spec.get("external") is True or spec.get("driver", "local") != "local":
            raise host.LocalDockerError("external or remote recovery volume not admitted")
        if service not in services:
            raise host.LocalDockerError("persistent volume owner service missing")
        mounts = services[service].get("volumes")
        if (not isinstance(mounts, list) or len([
            m for m in mounts if isinstance(m, dict)
            and m.get("type") == "volume" and m.get("source") == physical
            and m.get("target") == target and m.get("read_only") is not True
        ]) != 1):
            raise host.LocalDockerError("actual application volume owner mapping changed")
        observed[logical] = physical
    return observed


def _volume_metadata(physical: str, logical: str, project: str, root: Path) -> None:
    raw = host._run(
        ["docker", "volume", "inspect", physical],
        root=root, capture=True,
    )
    info = _json(raw, limit=16384)
    if not isinstance(info, list) or len(info) != 1 or not isinstance(info[0], dict):
        raise host.LocalDockerError("Docker volume inspection must yield exactly one identity")
    row = info[0]
    labels = row.get("Labels")
    if (row.get("Name") != physical or row.get("Driver") != "local"
            or row.get("Scope") != "local"
            or not isinstance(labels, dict)
            or labels.get(_LABEL_PROJECT) != project
            or labels.get(_LABEL_VOLUME) != logical
            or not isinstance(row.get("Mountpoint"), str)
            or not row["Mountpoint"].startswith("/")):
        raise host.LocalDockerError("application recovery volume ownership is unverified")
    if row.get("Options") not in (None, {}):
        raise host.LocalDockerError("custom volume driver options are unqualified")


def _running_attachments(physical: str, root: Path) -> int:
    output = host._run(
        ["docker", "ps", "--no-trunc",
         "--filter", "volume=" + physical, "--format", "{{.ID}}"],
        root=root, capture=True,
    )
    if not isinstance(output, str) or len(output) > 8192:
        raise host.LocalDockerError("running application volume attachment inventory unavailable")
    ids = [line.strip() for line in output.splitlines() if line.strip()]
    if len(ids) > 128 or any(not _ID.fullmatch(cid) for cid in ids):
        raise host.LocalDockerError("running application volume attachment IDs invalid")
    if len(set(ids)) != len(ids):
        raise host.LocalDockerError("running volume attachment inventory contains duplicates")
    return len(ids)


def preflight_application_recovery(
    mode: str, root: Path = host.ROOT,
) -> dict[str, object]:
    """Read real Docker daemon state, without reading or modifying file bytes."""
    if mode not in host.GPU_OVERLAYS:
        raise host.LocalDockerError("invalid local AI accelerator profile")
    prefix = host.compose_command(mode, root)
    topology = _json(host._run(
        [*prefix, "config", "--format", "json"], root=root, capture=True,
    ), limit=2 * 1024 * 1024)
    if not isinstance(topology, dict):
        raise host.LocalDockerError("effective Compose topology unavailable")
    # The complete local-only network and named-volume policies still apply.
    host._validate_config(mode, topology)
    project = topology.get("name")
    names = _expected_volumes(topology)
    if len(names) not in (4, 5):
        raise host.LocalDockerError("application volume inventory is incomplete")
    attachments = 0
    for logical, physical in sorted(names.items()):
        _volume_metadata(physical, logical, project, root)
        attachments += _running_attachments(physical, root)
    # Re-scan after all reads as a best-effort concurrency check. This is NOT
    # an exclusive lock, filesystem freeze or reliable writer-quiescence proof.
    for logical, physical in sorted(names.items()):
        attachments += _running_attachments(physical, root)
    return {
        "schema": _SCHEMA,
        "status": "volumes_observed_not_application_recovery_qualified",
        "mode": mode,
        "required_volumes_observed": len(_REQUIRED),
        "total_application_volumes_observed": len(names),
        "optional_chroma_volume_present": "chroma_data" in names,
        "running_volume_attachments_observed": attachments,
        "no_running_attachments_observed": attachments == 0,
        "exclusive_writer_quiescence_verified": False,
        "database_consistency_verified": False,
        "cross_store_snapshot_atomic": False,
        "credentials_exported": False,
        "content_copied": False,
        "restore_executed": False,
        "recovery_qualified": False,
        "protected_jeeves_qualified": False,
    }


__all__ = ["preflight_application_recovery"]

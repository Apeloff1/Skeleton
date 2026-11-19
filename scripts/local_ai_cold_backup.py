"""Opt-in offline Docker application-state volume copy and separate rehash.

This is a physical *byte* copy, not Mongo/SQLite/Chroma crash consistency,
logical application recovery, validated writer quiescence or a restore.
The user must explicitly opt into a non-atomic cold-copy attempt, after
independently stopping all administrative writers. Source volumes are mounted
readonly and have no network, only a new private destination is writable.

No service stop, Docker pull, live migration, database reconfiguration,
volume deletion, restore or false protected-chat activation occurs.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from scripts import local_ai_docker as host
from scripts import local_ai_recovery as source
from scripts import local_ai_volume_copy as worker

SCHEMA = "skeleton.local-ai.docker.application-state-cold-bytes.v1"
RECEIPT = "application-state.receipt.json"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _private_root(target: Path, *, must_exist: bool) -> Path:
    if not isinstance(target, Path) or not target.is_absolute():
        raise host.LocalDockerError("cold-copy destination must be an absolute private path")
    if any(c in str(target) for c in (",", "\x00", "\n", "\r", "=")) or len(str(target)) > 2048:
        raise host.LocalDockerError("cold-copy destination path is unsupported")
    if not target.parent.is_dir() or target.parent.is_symlink():
        raise host.LocalDockerError("cold-copy parent is unavailable")
    parent = target.parent
    try:
        st = parent.lstat()
        if (not hasattr(os, "getuid") or not stat.S_ISDIR(st.st_mode)
                or st.st_uid != os.getuid() or st.st_mode & 0o077):
            raise host.LocalDockerError("cold-copy parent must be operator-owned 0700")
        for path in (target, *target.parents):
            if path.is_symlink():
                raise host.LocalDockerError("cold-copy destination must not contain symlinks")
        if must_exist:
            st = target.lstat()
            if (not stat.S_ISDIR(st.st_mode) or st.st_mode & 0o077
                    or st.st_uid != os.getuid()):
                raise host.LocalDockerError("cold-copy archive is not an owned private directory")
        elif target.exists() or target.is_symlink():
            raise host.LocalDockerError("cold-copy destination must be unused")
    except OSError:
        raise host.LocalDockerError("private cold-copy path unavailable") from None
    return target


def _image_identity(image: str, root: Path) -> str:
    if not isinstance(image, str) or not image or len(image) > 250:
        raise host.LocalDockerError("canonical image identity unavailable")
    actual = host._run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image],
        root=root, capture=True,
    ).strip()
    if not _IMAGE.fullmatch(actual):
        raise host.LocalDockerError("local image digest did not match a physical Docker image")
    return actual


def _run_worker(
    image_id: str, logical: str, volume: str | None,
    destination: Path, *, action: str, root: Path,
    source_mountpoint: str | None = None,
    run_as: str = "0:0",
) -> dict[str, Any]:
    if action not in ("copy", "verify") or logical not in worker.ROLES:
        raise host.LocalDockerError("unsupported offline state archive operation")
    if not _IMAGE.fullmatch(image_id):
        raise host.LocalDockerError("cold-copy worker image digest is invalid")
    # Use the operator-owned archive UID/GID for private destination writes.
    # Synthetic CI uses the runner identity; a root-owned production archive
    # continues to run as root with capabilities removed. Never accept Docker
    # --user flags or arbitrary account names from untrusted input.
    if (not isinstance(run_as, str)
            or not re.fullmatch(r"(?:0|[1-9][0-9]{0,9}):(?:0|[1-9][0-9]{0,9})", run_as)
            or any(int(piece) > 2147483647 for piece in run_as.split(":"))):
        raise host.LocalDockerError("cold-copy worker user identity invalid")
    if volume is not None and not source._NAME.fullmatch(volume):
        raise host.LocalDockerError("untrusted recovery volume identity")
    if (action == "copy" and (volume is None or source_mountpoint is None)):
        raise host.LocalDockerError("cold-copy source must be an inspected existing bind")
    if (action == "verify" and (volume is not None or source_mountpoint is not None)):
        raise host.LocalDockerError("archive verification cannot mount a source volume")
    # No docker.sock, auth/secrets, external network, container privilege
    # escalation or mutable original volume is admitted. Local image ID is
    # immutable, so a retag cannot replace the inspected copy worker.
    command = [
        "docker", "run", "--rm", "--pull=never", "--network=none",
        "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--user=" + run_as,
        "--memory=4g", "--cpus=2", "--pids-limit=96",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
        "--mount=type=bind,source=" + str(destination)
            + ",target=/archive" + (",readonly" if action == "verify" else ""),
    ]
    if action == "copy":
        if volume is None:
            raise host.LocalDockerError("offline copy requires a physical source")
        # The default Docker type=volume mount creates absent volumes.
        # Bind only the *existing* canonical local daemon data mountpoint
        # instead; a disappeared source must fail, not create empty state.
        inspected = source._validated_mountpoint(volume, source_mountpoint)
        command.append(
            "--mount=type=bind,source=" + inspected
            + ",target=/source,readonly"
        )
    command += [
        "--entrypoint=python", image_id,
        "-m", "scripts.local_ai_volume_copy", action,
        "--role", logical, "--archive", "/archive",
    ]
    raw = host._run(command, root=root, capture=True)
    if not isinstance(raw, str) or len(raw) > 8192:
        raise host.LocalDockerError("offline volume copy evidence unavailable")
    try:
        result = json.loads(raw)
    except (ValueError, TypeError):
        raise host.LocalDockerError("offline volume copy receipt is malformed") from None
    if not isinstance(result, dict) or result.pop("ok", None) is not True:
        raise host.LocalDockerError("offline volume copy rejected")
    expected = worker._receipt(logical, count=0, total=0, digest="0"*64)
    if (set(result) != set(expected)
            or result.get("schema") != worker.SCHEMA
            or result.get("volume_role") != logical
            or result.get("status") != "volume_bytes_copied_not_database_consistency_qualified"
            or not isinstance(result.get("manifest_sha256"), str)
            or not _HEX.fullmatch(result["manifest_sha256"])
            or type(result.get("files")) is not int
            or not 0 <= result["files"] <= worker.MAX_ENTRIES
            or type(result.get("bytes")) is not int
            or not 0 <= result["bytes"] <= worker.MAX_TOTAL_BYTES
            or any(result.get(key) is not False for key in (
                "cross_store_snapshot_atomic", "application_restore_qualified",
                "protected_jeeves_qualified",
            ))):
        raise host.LocalDockerError("offline volume report has unauthorized scope")
    return result


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _receipt(volume_results: dict[str, dict[str, Any]], image_id: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "physical_cold_bytes_verified_not_application_recovery_qualified",
        "archive_kind": "offline_docker_application_state",
        "worker_image_id": image_id,
        "roles": sorted(volume_results),
        "volumes": volume_results,
        "total_files": sum(x["files"] for x in volume_results.values()),
        "total_bytes": sum(x["bytes"] for x in volume_results.values()),
        "model_artifacts_included": False,
        "database_consistency_verified": False,
        "cross_store_snapshot_atomic": False,
        "exclusive_writer_quiescence_verified": False,
        "restore_executed": False,
        "application_recovery_qualified": False,
        "protected_jeeves_qualified": False,
    }


def _write_receipt(destination: Path, value: dict[str, Any]) -> None:
    data = _canonical_bytes(value)
    checksum = hashlib.sha256(data).hexdigest()
    full = _canonical_bytes({**value, "receipt_sha256": checksum})
    path = destination / RECEIPT
    with os.fdopen(os.open(
        path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
        | getattr(os, "O_NOFOLLOW", 0), 0o600,
    ), "wb", buffering=0) as handle:
        handle.write(full)
        os.fsync(handle.fileno())


def _read_receipt(destination: Path) -> dict:
    location = destination / RECEIPT
    try:
        st = location.lstat()
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or st.st_size > 32768 or st.st_mode & 0o077):
            raise host.LocalDockerError("cold-copy receipt file is unsafe")
        data = json.loads(location.read_bytes())
        if not isinstance(data, dict):
            raise ValueError("receipt object")
        claimed = data.pop("receipt_sha256", None)
        if not isinstance(claimed, str) or not _HEX.fullmatch(claimed):
            raise ValueError("digest")
        if hashlib.sha256(_canonical_bytes(data)).hexdigest() != claimed:
            raise ValueError("checksum")
        return data
    except (ValueError, TypeError, OSError, UnicodeError):
        raise host.LocalDockerError("offline application archive receipt invalid") from None


def verify_application_cold_backup(destination: Path, *, root: Path = host.ROOT) -> dict:
    target = _private_root(destination, must_exist=True)
    report = _read_receipt(target)
    roles = report.get("roles")
    volumes = report.get("volumes")
    image_id = report.get("worker_image_id")
    if (report.get("schema") != SCHEMA or
            report.get("status") != "physical_cold_bytes_verified_not_application_recovery_qualified" or
            report.get("archive_kind") != "offline_docker_application_state" or
            not isinstance(image_id, str) or not _IMAGE.fullmatch(image_id) or
            not isinstance(roles, list) or not isinstance(volumes, dict) or
            not source._REQUIRED.issubset(roles) or
            len(roles) not in (4, 5) or roles != sorted(roles) or
            set(roles) != set(volumes) or
            not set(roles).issubset(worker.ROLES) or
            type(report.get("total_files")) is not int or
            type(report.get("total_bytes")) is not int or
            report.get("model_artifacts_included") is not False or
            any(report.get(key) is not False for key in (
                "database_consistency_verified", "cross_store_snapshot_atomic",
                "exclusive_writer_quiescence_verified", "restore_executed",
                "application_recovery_qualified", "protected_jeeves_qualified",
            )) or set(report) != set(_receipt({
                role: worker._receipt(role, count=0, total=0, digest="0"*64)
                for role in source._REQUIRED
            }, image_id))):
        raise host.LocalDockerError("application byte archive cannot claim recovery authority")
    if {item.name for item in target.iterdir()} != set(roles) | {RECEIPT}:
        raise host.LocalDockerError("cold-copy archive has undeclared entries")
    worker_identity = f"{os.getuid()}:{os.getgid()}"
    verified: dict[str, dict] = {}
    for role in roles:
        proof = _run_worker(image_id, role, None, target,
                            action="verify", root=root, run_as=worker_identity)
        if proof != volumes[role]:
            raise host.LocalDockerError("application archive bytes differ from approved copy")
        verified[role] = proof
    expected = _receipt(verified, image_id)
    if expected != report:
        raise host.LocalDockerError("application archive total differs from verified volumes")
    return {
        "schema": SCHEMA,
        "status": "offline_volume_bytes_independently_rehashed_not_restore_qualified",
        "volumes_verified": len(roles),
        "files_verified": report["total_files"],
        "bytes_verified": report["total_bytes"],
        "cross_store_snapshot_atomic": False,
        "application_recovery_qualified": False,
        "protected_jeeves_qualified": False,
    }


def cold_backup_application(
    mode: str, destination: Path, *,
    acknowledged_non_atomic: bool = False,
    root: Path = host.ROOT,
) -> dict:
    if acknowledged_non_atomic is not True:
        raise host.LocalDockerError("cold backup requires explicit acknowledgement of non-atomic volume copies")
    target = _private_root(destination, must_exist=False)
    observed = source.preflight_application_recovery(mode, root)
    if observed.get("no_running_attachments_observed") is not True:
        raise host.LocalDockerError("running Docker volume attachments prohibit cold copying")
    prefix = host.compose_command(mode, root)
    raw = host._run([*prefix, "config", "--format", "json"], root=root, capture=True)
    try:
        topology = json.loads(raw)
    except (ValueError, TypeError):
        raise host.LocalDockerError("cold-copy canonical topology unavailable") from None
    host._validate_config(mode, topology)
    volume_names = source._expected_volumes(topology)
    # Independently re-validate every observed volume immediately before its
    # private, explicitly acknowledged byte copy.
    available: dict[str, tuple[str, str]] = {}
    for logical, name in sorted(volume_names.items()):
        if not source._volume_exists(name, root):
            if logical in source._REQUIRED:
                raise host.LocalDockerError("mandatory application volume disappeared")
            continue
        daemon_source = source._volume_metadata(name, logical, topology["name"], root)
        if source._running_attachments(name, root):
            raise host.LocalDockerError("application state became active during cold-copy admission")
        available[logical] = (name, daemon_source)
    if (len(available) != observed["total_application_volumes_observed"]
            or not source._REQUIRED.issubset(available)):
        raise host.LocalDockerError("application volume inventory changed after cold preflight")
    image = host._validate_config(mode, topology)["image"]
    image_id = _image_identity(image, root)
    target.mkdir(mode=0o700)
    results: dict[str, dict] = {}
    worker_identity = f"{os.getuid()}:{os.getgid()}"
    try:
        for logical, (name, inspected_path) in sorted(available.items()):
            if source._running_attachments(name, root):
                raise host.LocalDockerError("application writer appeared before volume copy")
            if source._volume_metadata(name, logical, topology["name"], root) != inspected_path:
                raise host.LocalDockerError("daemon volume data identity changed before copy")
            copied = _run_worker(
                image_id, logical, name, target, action="copy", root=root,
                source_mountpoint=inspected_path,
                run_as=worker_identity,
            )
            if (not source._volume_exists(name, root)
                    or source._volume_metadata(name, logical, topology["name"], root) != inspected_path):
                raise host.LocalDockerError("daemon volume data identity changed after copy")
            if source._running_attachments(name, root):
                raise host.LocalDockerError("application writer appeared after volume copy")
            verified = _run_worker(
                image_id, logical, None, target, action="verify", root=root,
                run_as=worker_identity,
            )
            if copied != verified:
                raise host.LocalDockerError("independent volume byte rehash differs")
            results[logical] = copied
        # Check all mandatory and optional volumes one final time before any
        # qualifying byte receipt is written; cannot prove external quiescence.
        if any(
            not source._volume_exists(name, root)
            or source._volume_metadata(name, logical, topology["name"], root) != mount
            or source._running_attachments(name, root)
            for logical, (name, mount) in available.items()
        ):
            raise host.LocalDockerError("application volume became active before archive sealing")
        _write_receipt(target, _receipt(results, image_id))
        return verify_application_cold_backup(target, root=root)
    except Exception:
        # Preserve partial evidence. No user data or possibly valuable copied
        # bytes is automatically deleted; missing final receipt = not verified.
        raise host.LocalDockerError(
            "offline Docker state copy incomplete; private partial archive preserved"
        ) from None


__all__ = ["cold_backup_application", "verify_application_cold_backup"]

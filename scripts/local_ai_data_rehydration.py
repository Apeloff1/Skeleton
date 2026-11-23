#!/usr/bin/env python3
"""Rehydrate an offline Docker state archive into NEW private host directories.

This is a byte-level restore rehearsal ONLY. No Docker volume creation,
container startup, database runtime, schema migration or Mongo crash
consistency is implied. Every source file is rehashed, copied exclusively,
and independently rehashed at its new destination. No symlinks, hardlinks,
special files, preexisting destinations, index drift or unsafe paths.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Mapping

from scripts import local_ai_cold_backup as cold
from scripts import local_ai_docker as host
from scripts import local_ai_volume_copy as worker

SCHEMA = "skeleton.local-ai.docker.offline-byte-rehydration.v1"
RECEIPT = "offline-rehydration.receipt.json"
HEX = re.compile(r"[0-9a-f]{64}\Z")
MAX_RECEIPT = 32768
MAX_PATH = 2048
CHUNK = 4 * 1024 * 1024


class RestoreRehearsalError(host.LocalDockerError):
    """The independent byte-restore rehearsal cannot be trusted."""


def _hash_private(path: Path, *, limit: int) -> str:
    try:
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_mode & 0o077 or not 0 < before.st_size <= limit):
            raise RestoreRehearsalError("archive receipt custody file invalid")
        digest = hashlib.sha256()
        with os.fdopen(os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        ), "rb", buffering=0) as handle:
            opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise RestoreRehearsalError("archive receipt identity changed")
            while True:
                data = handle.read(CHUNK)
                if not data:
                    break
                digest.update(data)
                if handle.tell() > limit:
                    raise RestoreRehearsalError("archive receipt size exceeded")
        after = path.lstat()
        fields = lambda x: (x.st_dev, x.st_ino, x.st_size,
                            x.st_mtime_ns, x.st_ctime_ns)
        if fields(before) != fields(after):
            raise RestoreRehearsalError("archive receipt changed during verification")
        return digest.hexdigest()
    except OSError:
        raise RestoreRehearsalError("archive receipt unavailable") from None


def _source(source: Path, expected_receipt_sha256: str) -> tuple[Path, dict]:
    archive = cold._private_root(source, must_exist=True)
    if (not isinstance(expected_receipt_sha256, str)
            or not HEX.fullmatch(expected_receipt_sha256)
            or _hash_private(archive / cold.RECEIPT, limit=MAX_RECEIPT)
            != expected_receipt_sha256):
        raise RestoreRehearsalError("independent cold archive receipt digest differs")
    report = cold._read_receipt(archive)
    roles = report.get("roles")
    volumes = report.get("volumes")
    image = report.get("worker_image_id")
    if (report.get("schema") != cold.SCHEMA
            or report.get("status") !=
                "physical_cold_bytes_verified_not_application_recovery_qualified"
            or not isinstance(roles, list)
            or len(roles) not in (4, 5)
            or sorted(roles) != roles
            or len(set(roles)) != len(roles)
            or not cold.source._REQUIRED.issubset(roles)
            or not worker.ROLES.issuperset(roles)
            or not isinstance(volumes, dict) or set(volumes) != set(roles)
            or not isinstance(image, str) or not cold._IMAGE.fullmatch(image)
            or report.get("model_artifacts_included") is not False
            or report.get("database_consistency_verified") is not False
            or report.get("cross_store_snapshot_atomic") is not False
            or report.get("application_recovery_qualified") is not False):
        raise RestoreRehearsalError("source archive falsely claims restoration authority")
    if {entry.name for entry in archive.iterdir()} != set(roles) | {cold.RECEIPT}:
        raise RestoreRehearsalError("source archive has unexpected entries")
    seen: dict[str, dict] = {}
    for role in roles:
        measured = worker.verify_volume(role, archive)
        if measured != volumes[role]:
            raise RestoreRehearsalError("source archive volume byte custody differs")
        seen[role] = measured
    if cold._receipt(seen, image) != report:
        raise RestoreRehearsalError("cold archive aggregate receipt differs")
    return archive, report


def _member(name: object) -> str:
    if not isinstance(name, str) or not name or len(name) > worker.MAX_PATH_BYTES:
        raise RestoreRehearsalError("restored file path exceeds admitted bounds")
    path = PurePosixPath(name)
    if (path.is_absolute() or any(part in ("", ".", "..") for part in name.split("/"))
            or str(path) != name or name in (worker.MANIFEST, worker.RECEIPT)
            or "\x00" in name):
        raise RestoreRehearsalError("restored file path is unsafe")
    return name


def _rehydrate_one(archive: Path, target: Path, role: str,
                   expected: Mapping[str, Any]) -> dict[str, Any]:
    src = archive / role
    dst = target / role
    if dst.exists() or dst.is_symlink():
        raise RestoreRehearsalError("restore destination volume already exists")
    dst.mkdir(mode=0o700)
    manifest = src / worker.MANIFEST
    count = 0
    size = 0
    with manifest.open("rb", buffering=CHUNK) as stream:
        while True:
            line = stream.readline(worker.MAX_PATH_BYTES * 3 + 1)
            if not line:
                break
            if len(line) > worker.MAX_PATH_BYTES * 3 or not line.endswith(b"\n"):
                raise RestoreRehearsalError("source restore index exceeds bounded record")
            try:
                row = json.loads(line)
            except (ValueError, TypeError, UnicodeError):
                raise RestoreRehearsalError("restore index row malformed") from None
            if not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}:
                raise RestoreRehearsalError("restore index row shape invalid")
            rel = _member(row["path"])
            expected_bytes = row["bytes"]
            expected_sha = row["sha256"]
            if (type(expected_bytes) is not int
                    or not 0 <= expected_bytes <= worker.MAX_FILE_BYTES
                    or not isinstance(expected_sha, str) or not HEX.fullmatch(expected_sha)):
                raise RestoreRehearsalError("restore index digest/size invalid")
            digest, length = worker._copy_one(src / rel, dst / rel)
            if (digest, length) != (expected_sha, expected_bytes):
                raise RestoreRehearsalError("archive changed while rehydrating bytes")
            digest2, length2 = worker._digest_file(dst / rel)
            if (digest2, length2) != (expected_sha, expected_bytes):
                raise RestoreRehearsalError("restored output does not match source digest")
            count += 1
            size += length
            if count > worker.MAX_ENTRIES or size > worker.MAX_TOTAL_BYTES:
                raise RestoreRehearsalError("restore byte inventory exceeds budget")
    # Compare actual bounded physical destination inventory against source's
    # independently verified stream without retaining millions of paths.
    physical = (item.as_posix() for item in worker._walk(dst))
    with manifest.open("rb", buffering=CHUNK) as stream:
        for line in stream:
            row = json.loads(line)
            if next(physical, None) != row["path"]:
                raise RestoreRehearsalError("rehydrated file set differs from archive")
    if next(physical, None) is not None:
        raise RestoreRehearsalError("rehydrated output contains surprise files")
    if (count != expected["files"] or size != expected["bytes"]):
        raise RestoreRehearsalError("rehydrated byte tally differs from source")
    return {"role": role, "files": count, "bytes": size,
            "source_manifest_sha256": expected["manifest_sha256"],
            "independent_destination_rehash": True}


def _receipt(source_sha: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    value = {
        "schema": SCHEMA,
        "status": "all_cold_archive_files_rehydrated_not_database_restored",
        "source_receipt_file_sha256": source_sha,
        "roles": [row["role"] for row in rows],
        "volumes": rows,
        "total_files": sum(row["files"] for row in rows),
        "total_bytes": sum(row["bytes"] for row in rows),
        "external_volumes_created": False,
        "source_archive_mutated": False,
        "docker_daemon_used": False,
        "database_process_started": False,
        "sqlite_consistency_verified": False,
        "mongo_consistency_verified": False,
        "chroma_consistency_verified": False,
        "cross_store_snapshot_atomic": False,
        "application_restore_qualified": False,
        "protected_chat_qualified": False,
        "release_qualified": False,
    }
    value["receipt_sha256"] = hashlib.sha256(
        cold._canonical_bytes(value)
    ).hexdigest()
    return value


def rehearse_byte_restore(source: Path, destination: Path, *,
                          expected_receipt_sha256: str) -> dict[str, Any]:
    """Create-only private host rehydration, never a Docker volume restore."""
    archive, source_receipt = _source(source, expected_receipt_sha256)
    target = cold._private_root(destination, must_exist=False)
    if (target == archive or archive in target.parents
            or target in archive.parents):
        raise RestoreRehearsalError("restore destination intersects source archive")
    target.mkdir(mode=0o700)
    results: list[dict[str, Any]] = []
    try:
        for role in source_receipt["roles"]:
            results.append(_rehydrate_one(
                archive, target, role, source_receipt["volumes"][role]
            ))
        receipt = _receipt(expected_receipt_sha256, results)
        name = target / RECEIPT
        content = cold._canonical_bytes(receipt)
        with os.fdopen(os.open(
            name, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
            getattr(os, "O_NOFOLLOW", 0), 0o600
        ), "wb") as output:
            if output.write(content) != len(content):
                raise RestoreRehearsalError("restore rehearsal receipt short write")
            output.flush()
            os.fsync(output.fileno())
        return verify_rehydration(source, target,
                                  expected_receipt_sha256=expected_receipt_sha256)
    except Exception:
        raise RestoreRehearsalError(
            "byte rehydration incomplete; partial private output preserved"
        ) from None


def verify_rehydration(source: Path, destination: Path, *,
                       expected_receipt_sha256: str) -> dict[str, Any]:
    """Independently verify source and rehydrated destination, no state writes."""
    archive, source_receipt = _source(source, expected_receipt_sha256)
    target = cold._private_root(destination, must_exist=True)
    if (target == archive or archive in target.parents
            or target in archive.parents):
        raise RestoreRehearsalError("restore destination intersects source archive")
    if {x.name for x in target.iterdir()} != set(source_receipt["roles"]) | {RECEIPT}:
        raise RestoreRehearsalError("restore output has surprise members")
    report = json.loads((target / RECEIPT).read_bytes())
    expected_rows: list[dict[str, Any]] = []
    for role in source_receipt["roles"]:
        original = archive / role
        restored = target / role
        rows: list[str] = []
        manifest = original / worker.MANIFEST
        with manifest.open("rb") as stream:
            original_entries = (json.loads(line) for line in stream)
            observed_paths = (path.as_posix() for path in worker._walk(restored))
            count = 0
            total = 0
            for row in original_entries:
                rel = _member(row["path"])
                if next(observed_paths, None) != rel:
                    raise RestoreRehearsalError("restore output file names differ")
                sha, size = worker._digest_file(restored / rel)
                if (sha, size) != (row["sha256"], row["bytes"]):
                    raise RestoreRehearsalError("restore output byte digest differs")
                count += 1
                total += size
                if count > worker.MAX_ENTRIES or total > worker.MAX_TOTAL_BYTES:
                    raise RestoreRehearsalError("restore verification size limit")
            if next(observed_paths, None) is not None:
                raise RestoreRehearsalError("restored directory gained unindexed files")
        if (count, total) != (
            source_receipt["volumes"][role]["files"],
            source_receipt["volumes"][role]["bytes"]
        ):
            raise RestoreRehearsalError("rehydration output volume tally differs")
        expected_rows.append({
            "role": role, "files": count, "bytes": total,
            "source_manifest_sha256":
                source_receipt["volumes"][role]["manifest_sha256"],
            "independent_destination_rehash": True,
        })
    expected = _receipt(expected_receipt_sha256, expected_rows)
    if report != expected:
        raise RestoreRehearsalError("restore receipt has changed or escalated authority")
    if _hash_private(target / RECEIPT, limit=MAX_RECEIPT) != hashlib.sha256(
        cold._canonical_bytes(expected)
    ).hexdigest():
        raise RestoreRehearsalError("restored receipt bytes differ from canonical")
    return expected


__all__ = ["rehearse_byte_restore", "verify_rehydration"]

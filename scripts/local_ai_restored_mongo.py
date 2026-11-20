#!/usr/bin/env python3
"""Read-only restored MongoDB WiredTiger *file-envelope* custody.

Only operates on a private, independently rehydrated offline cold copy.
This module NEVER starts mongod, opens a Mongo client, parses BSON or a
WiredTiger page, replays a journal, reads a private document, or repairs data.

File names, file sizes, identity, and SHA-256 hashes can establish physical
custody of a *supported historical layout*, not Mongo logical consistency.
Mongo runtime recovery, snapshot atomicity, source quiescence, transaction
replay, epoch enrollment and release remain explicitly unqualified.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
import time
from typing import Any

from scripts import local_ai_data_rehydration as restored
from scripts import local_ai_docker as host

SCHEMA = "skeleton.local-ai.docker.restored-mongo-wiredtiger-file-custody.v1"
_REQUIRED = frozenset((
    "WiredTiger", "WiredTiger.turtle", "WiredTiger.wt",
    "storage.bson", "_mdb_catalog.wt",
))
_OPTIONAL = frozenset((
    "WiredTiger.lock", "WiredTigerHS.wt", "WiredTigerLAS.wt",
    "WiredTiger.basecfg", "sizeStorer.wt", "mongod.lock",
))
_DIRECTORIES = frozenset(("journal", "diagnostic.data"))
_DATA = re.compile(r"(?:collection|index)-[A-Za-z0-9_-]{1,160}\.wt\Z")
_JOURNAL = re.compile(
    r"WiredTiger(?:Log|Preplog|Tmplog)\.[0-9]{10}\Z"
)
_MAX_ROOT = 100_000
_MAX_JOURNAL = 8192
_MAX_FILE_BYTES = 16 * 1024 ** 4
_MAX_TOTAL_BYTES = 32 * 1024 ** 4
_MAX_SECONDS = 120
_CHUNK = 4 * 1024 * 1024
_HEX = re.compile(r"[a-f0-9]{64}\Z")


class MongoWiredTigerCustodyError(host.LocalDockerError):
    """Restored MongoDB file envelope is incomplete or untrustworthy."""


def _state(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_size,
        info.st_mtime_ns, info.st_ctime_ns, info.st_nlink,
    )


def _owned_file(info: os.stat_result, *, allow_empty: bool) -> None:
    if (
        not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
        or info.st_mode & 0o077
        or not 0 <= info.st_size <= _MAX_FILE_BYTES
        or (not allow_empty and info.st_size == 0)
    ):
        raise MongoWiredTigerCustodyError(
            "restored Mongo member not a private bounded regular file"
        )


def _owned_directory(info: os.stat_result) -> None:
    if (
        not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077
        or info.st_nlink < 1
    ):
        raise MongoWiredTigerCustodyError(
            "restored Mongo directory not private and bounded"
        )


def _directory_fd(path: Path, *, parent_fd: int | None = None) -> int:
    """Pin a directory inode; never follow a symlink through its final name."""
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise MongoWiredTigerCustodyError(
            "secure descriptor-relative Mongo inventory unsupported"
        )
    try:
        if parent_fd is None:
            original = os.stat(path, follow_symlinks=False)
            fd = os.open(
                path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0),
            )
        else:
            original = os.stat(str(path), dir_fd=parent_fd,
                               follow_symlinks=False)
            fd = os.open(
                str(path),
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent_fd,
            )
        try:
            _owned_directory(original)
            if _state(original) != _state(os.fstat(fd)):
                raise MongoWiredTigerCustodyError(
                    "restored Mongo directory changed during open"
                )
            return fd
        except BaseException:
            os.close(fd)
            raise
    except MongoWiredTigerCustodyError:
        raise
    except OSError:
        raise MongoWiredTigerCustodyError(
            "restored Mongo directory identity unavailable"
        ) from None


def _stable_dir(fd: int, path: Path, *, parent_fd: int | None = None) -> None:
    try:
        info = (os.stat(path, follow_symlinks=False)
                if parent_fd is None else
                os.stat(str(path), dir_fd=parent_fd, follow_symlinks=False))
        _owned_directory(info)
        if _state(info) != _state(os.fstat(fd)):
            raise MongoWiredTigerCustodyError(
                "restored Mongo directory swapped during inventory"
            )
    except MongoWiredTigerCustodyError:
        raise
    except OSError:
        raise MongoWiredTigerCustodyError(
            "restored Mongo directory changed during inventory"
        ) from None


def _entries(fd: int, *, max_entries: int) -> dict[str, bool]:
    """Bound directory traversal before any member content is inspected."""
    names: dict[str, bool] = {}
    try:
        with os.scandir(fd) as iterator:
            for item in iterator:
                name = item.name
                if (
                    not isinstance(name, str)
                    or not 0 < len(name) <= 200
                    or "\x00" in name or "/" in name
                    or name in (".", "..") or name in names
                ):
                    raise MongoWiredTigerCustodyError(
                        "Mongo restored member name outside bounded scope"
                    )
                if len(names) == max_entries:
                    raise MongoWiredTigerCustodyError(
                        "restored Mongo directory entry budget exceeded"
                    )
                is_dir = item.is_dir(follow_symlinks=False)
                if not is_dir and not item.is_file(follow_symlinks=False):
                    raise MongoWiredTigerCustodyError(
                        "restored Mongo linked/special entry forbidden"
                    )
                names[name] = is_dir
    except MongoWiredTigerCustodyError:
        raise
    except OSError:
        raise MongoWiredTigerCustodyError(
            "restored Mongo directory listing unavailable"
        ) from None
    return names


def _hash_file(fd: int, name: str, *, deadline: float,
               allow_empty: bool = False) -> tuple[str, int]:
    """Stream bytes only from an O_NOFOLLOW openat file on the pinned fd."""
    if (
        not isinstance(name, str) or not 0 < len(name) <= 200
        or "/" in name or "\x00" in name or name in (".", "..")
    ):
        raise MongoWiredTigerCustodyError("Mongo file member scope invalid")
    try:
        before = os.stat(name, dir_fd=fd, follow_symlinks=False)
        _owned_file(before, allow_empty=allow_empty)
        opened = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0), dir_fd=fd,
        )
        with os.fdopen(opened, "rb", buffering=0) as stream:
            if _state(os.fstat(stream.fileno())) != _state(before):
                raise MongoWiredTigerCustodyError(
                    "Mongo file inode changed during admission"
                )
            digest = hashlib.sha256()
            amount = 0
            while True:
                if time.monotonic() > deadline:
                    raise MongoWiredTigerCustodyError(
                        "Mongo offline byte inventory exceeded deadline"
                    )
                chunk = stream.read(_CHUNK)
                if not chunk:
                    break
                amount += len(chunk)
                if amount > before.st_size or amount > _MAX_FILE_BYTES:
                    raise MongoWiredTigerCustodyError(
                        "Mongo offline byte inventory exceeded budget"
                    )
                digest.update(chunk)
            if _state(os.fstat(stream.fileno())) != _state(before):
                raise MongoWiredTigerCustodyError(
                    "Mongo file inode modified during hash"
                )
        if (
            amount != before.st_size
            or _state(os.stat(name, dir_fd=fd, follow_symlinks=False))
               != _state(before)
        ):
            raise MongoWiredTigerCustodyError(
                "Mongo restored file identity drifted during hash"
            )
        return digest.hexdigest(), amount
    except MongoWiredTigerCustodyError:
        raise
    except OSError:
        raise MongoWiredTigerCustodyError(
            "Mongo restored file not safely readable"
        ) from None


def _classify_root(name: str, is_dir: bool) -> str:
    if is_dir:
        if name not in _DIRECTORIES:
            raise MongoWiredTigerCustodyError(
                "unsupported restored Mongo directory layout"
            )
        return name
    if name in _REQUIRED or name in _OPTIONAL:
        return "metadata"
    if _DATA.fullmatch(name):
        return "collection" if name.startswith("collection-") else "index"
    raise MongoWiredTigerCustodyError(
        "unrecognized restored Mongo WiredTiger file layout"
    )


def _recovery_archive(
    source: Path, destination: Path, sha256: str,
) -> dict[str, Any]:
    try:
        report = restored.verify_rehydration(
            source, destination, expected_receipt_sha256=sha256,
        )
    except Exception:
        raise MongoWiredTigerCustodyError(
            "independent cold archive and rehydration custody unavailable"
        ) from None
    roles = report.get("roles") if isinstance(report, dict) else None
    if (
        not isinstance(roles, list)
        or any(type(role) is not str for role in roles)
        or roles != sorted(roles)
        or report.get("schema") != restored.SCHEMA
        or report.get("status") != "all_cold_archive_files_rehydrated_not_database_restored"
        or report.get("source_receipt_file_sha256") != sha256
        or set(roles) not in (
            {"mongo_data", "mongo_config", "backend_data", "skeleton_data"},
            {"mongo_data", "mongo_config", "backend_data", "skeleton_data",
             "chroma_data"},
        )
        or report.get("database_process_started") is not False
        or report.get("docker_daemon_used") is not False
        or report.get("mongo_consistency_verified") is not False
        or report.get("cross_store_snapshot_atomic") is not False
        or report.get("application_restore_qualified") is not False
        or report.get("external_volumes_created") is not False
        or report.get("source_archive_mutated") is not False
        or report.get("sqlite_consistency_verified") is not False
        or report.get("chroma_consistency_verified") is not False
        or report.get("protected_chat_qualified") is not False
        or report.get("release_qualified") is not False
        or type(report.get("receipt_sha256")) is not str
        or _HEX.fullmatch(report["receipt_sha256"]) is None
    ):
        raise MongoWiredTigerCustodyError(
            "cold archive attempted to claim Mongo logical recovery"
        )
    return report


def inspect_restored_mongo(
    source: Path, destination: Path, *,
    expected_receipt_sha256: str,
) -> dict[str, object]:
    """Static WiredTiger journal and data-file custody without page parsing."""
    if (
        type(expected_receipt_sha256) is not str
        or _HEX.fullmatch(expected_receipt_sha256) is None
    ):
        raise MongoWiredTigerCustodyError("independent cold archive digest invalid")
    first = _recovery_archive(source, destination, expected_receipt_sha256)
    try:
        target = restored.cold._private_root(destination, must_exist=True)
    except Exception:
        raise MongoWiredTigerCustodyError(
            "private restored Mongo root unavailable"
        ) from None
    deadline = time.monotonic() + _MAX_SECONDS
    root_path = target / "mongo_data"
    root_fd = _directory_fd(root_path)
    try:
        members = _entries(root_fd, max_entries=_MAX_ROOT)
        categories = {name: _classify_root(name, is_dir)
                      for name, is_dir in members.items()}
        if not _REQUIRED.issubset(categories):
            raise MongoWiredTigerCustodyError(
                "restored Mongo WiredTiger mandatory catalog files missing"
            )
        count = 0
        bytes_total = 0
        collections = 0
        indexes = 0
        journal_files = 0
        digest = hashlib.sha256(b"skeleton.mongo.wiredtiger.envelope.v1\x00")

        def record(name: str, sha: str, size: int) -> None:
            nonlocal count, bytes_total
            count += 1
            bytes_total += size
            if count > _MAX_ROOT + _MAX_JOURNAL or bytes_total > _MAX_TOTAL_BYTES:
                raise MongoWiredTigerCustodyError(
                    "restored Mongo data envelope exceeds budget"
                )
            digest.update(name.encode("ascii") + b"\x00")
            digest.update(size.to_bytes(8, "big"))
            digest.update(bytes.fromhex(sha))

        for name in sorted(members):
            kind = categories[name]
            if kind in _DIRECTORIES:
                continue
            sha, size = _hash_file(
                root_fd, name, deadline=deadline,
                allow_empty=name in ("WiredTiger.lock", "mongod.lock"),
            )
            record(name, sha, size)
            collections += int(kind == "collection")
            indexes += int(kind == "index")
        if "journal" in members:
            journal_fd = _directory_fd(Path("journal"), parent_fd=root_fd)
            try:
                journal_names = _entries(journal_fd, max_entries=_MAX_JOURNAL)
                if any(
                    directory or _JOURNAL.fullmatch(name) is None
                    for name, directory in journal_names.items()
                ):
                    raise MongoWiredTigerCustodyError(
                        "unrecognized Mongo journal layout cannot be replayed"
                    )
                for name in sorted(journal_names):
                    sha, size = _hash_file(journal_fd, name, deadline=deadline)
                    record("journal/" + name, sha, size)
                    journal_files += 1
                _stable_dir(journal_fd, Path("journal"), parent_fd=root_fd)
                if _entries(journal_fd, max_entries=_MAX_JOURNAL) != journal_names:
                    raise MongoWiredTigerCustodyError(
                        "Mongo journal changed during cold inspection"
                    )
            finally:
                os.close(journal_fd)
        # diagnostic.data is already byte-qualified by restore verifier,
        # but is not needed for WiredTiger file-envelope identity.
        _stable_dir(root_fd, root_path)
        if _entries(root_fd, max_entries=_MAX_ROOT) != members:
            raise MongoWiredTigerCustodyError(
                "restored Mongo data directory changed during inspection"
            )
    finally:
        os.close(root_fd)

    last = _recovery_archive(source, destination, expected_receipt_sha256)
    if last != first:
        raise MongoWiredTigerCustodyError(
            "cold source archive changed across Mongo inspection"
        )
    return {
        "schema": SCHEMA,
        "status": "wiredtiger_static_file_custody_only_not_mongod_recovery",
        "required_catalog_files_verified": len(_REQUIRED),
        "hashed_wiredtiger_files": count,
        "hashed_wiredtiger_bytes": bytes_total,
        "collection_files_observed": collections,
        "index_files_observed": indexes,
        "journal_files_observed": journal_files,
        "journal_file_bytes_present": journal_files > 0,
        "diagnostic_directory_present": "diagnostic.data" in members,
        "aggregate_file_fingerprint_sha256": digest.hexdigest(),
        "independent_cold_archive_verified_twice": True,
        "wiredtiger_page_parser_executed": False,
        "mongod_process_started": False,
        "mongo_journal_replayed": False,
        "mongo_logical_consistency_verified": False,
        "external_writer_quiescence_verified": False,
        "mongo_application_transactions_recovered": False,
        "sqlite_chroma_alignment_verified": False,
        "cross_store_snapshot_atomic": False,
        "application_restore_qualified": False,
        "protected_jeeves_chat_qualified": False,
        "release_authorized": False,
    }


__all__ = [
    "MongoWiredTigerCustodyError", "inspect_restored_mongo",
]

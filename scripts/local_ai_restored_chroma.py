#!/usr/bin/env python3
"""Read-only offline Chroma SQLite-to-HNSW *file custody* qualification.

Requires an independently verified cold byte archive and its new private
rehydration. Never connects to Chroma service, invokes index parsers, loads
pickles, executes arbitrary SQL or binds to a Docker volume. This gate
tests known legacy local-persistent HNSW file relationships and bytes only:
even a clean receipt CANNOT prove a usable vector graph, embedding replay,
WiredTiger recovery, cross-store atomicity, or protected chat readiness.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from typing import Any
from urllib.parse import quote
from uuid import UUID

from scripts import local_ai_data_rehydration as rehydrate
from scripts import local_ai_restored_sqlite as sqlite_gate
from scripts import local_ai_docker as host

SCHEMA = "skeleton.local-ai.docker.restored-chroma-hnsw-custody.v1"
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_INDEX = frozenset((
    "header.bin", "data_level0.bin", "length.bin", "link_lists.bin",
    "index_metadata.pickle",
))
_SQLITE = "chroma.sqlite3"
_VECTOR_TYPE = "urn:chroma:segment/vector/hnsw-local-persisted"
_MAX_SEGMENTS = 128
_MAX_CATALOG_ROWS = 512
_MAX_INDEX_FILE = 32 * 1024 ** 3
_MAX_TOTAL_BYTES = 128 * 1024 ** 3
_MAX_SECONDS = 120
_MAX_SQL_ROWS = 513


class ChromaCustodyError(host.LocalDockerError):
    """Read-only Chroma metadata/binary custody cannot be established."""


def _uuid(value: object) -> str:
    if (type(value) is not str or _UUID.fullmatch(value) is None):
        raise ChromaCustodyError("Chroma segment catalog identity invalid")
    try:
        if str(UUID(value)) != value:
            raise ChromaCustodyError("Chroma segment UUID not canonical")
    except (ValueError, TypeError, AttributeError):
        raise ChromaCustodyError("Chroma segment catalog identity invalid") from None
    return value


def _private(path: Path, *, directory: bool, max_bytes: int = _MAX_INDEX_FILE) -> tuple[int, ...]:
    try:
        attrs = path.lstat()
        if (
            (not stat.S_ISDIR(attrs.st_mode) if directory
             else not stat.S_ISREG(attrs.st_mode))
            or attrs.st_nlink < 1
            or (not directory and attrs.st_nlink != 1)
            or attrs.st_mode & 0o077
            or (not directory and not 0 < attrs.st_size <= max_bytes)
        ):
            raise ChromaCustodyError("restored Chroma member not bounded private file")
        return (
            attrs.st_dev, attrs.st_ino, attrs.st_mode,
            attrs.st_size, attrs.st_mtime_ns, attrs.st_ctime_ns,
        )
    except OSError:
        raise ChromaCustodyError("restored Chroma member unavailable") from None


def _catalog(path: Path, *, deadline: float) -> tuple[list[str], str]:
    """Query exact known SQLite columns; never parse Chroma pickle/graph."""
    original = _private(path, directory=False,
                        max_bytes=sqlite_gate._MAX_SQLITE_BYTES)
    sqlite_gate._require_no_sidecar(path)
    digest, size = sqlite_gate._integrity(path, deadline=deadline)
    try:
        uri = "file:" + quote(str(path), safe="/") + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True, timeout=0.0)) as db:
            db.enable_load_extension(False)
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA trusted_schema=OFF")
            db.set_progress_handler(
                lambda: 1 if time.monotonic() > deadline else 0, 4096,
            )
            columns = {
                r[1] for r in db.execute("PRAGMA table_info(segments)")
                if len(r) >= 2 and type(r[1]) is str
            }
            if not {"id", "type", "scope"}.issubset(columns):
                raise ChromaCustodyError(
                    "restored Chroma does not expose supported segment schema"
                )
            cursor = db.execute(
                "SELECT id, type, scope FROM segments LIMIT ?",
                (_MAX_SQL_ROWS,),
            )
            seen: set[str] = set()
            vector_ids: list[str] = []
            total_rows = 0
            for raw_id, raw_type, scope in cursor:
                total_rows += 1
                if total_rows > _MAX_CATALOG_ROWS:
                    raise ChromaCustodyError("restored Chroma segment catalog too large")
                segment_id = _uuid(raw_id)
                if segment_id in seen:
                    raise ChromaCustodyError("restored Chroma duplicate segment identity")
                seen.add(segment_id)
                if scope == "VECTOR":
                    if raw_type != _VECTOR_TYPE:
                        raise ChromaCustodyError(
                            "unrecognized persistent Chroma vector index format"
                        )
                    vector_ids.append(segment_id)
                    if len(vector_ids) > _MAX_SEGMENTS:
                        raise ChromaCustodyError("too many restored vector segments")
                elif scope not in ("METADATA", "RECORD"):
                    raise ChromaCustodyError("unknown Chroma catalog segment scope")
        sqlite_gate._require_no_sidecar(path)
        after_digest, after_size = sqlite_gate._integrity(
            path, deadline=deadline
        )
        if ((after_digest, after_size) != (digest, size)
                or _private(path, directory=False,
                            max_bytes=sqlite_gate._MAX_SQLITE_BYTES) != original):
            raise ChromaCustodyError("Chroma catalog bytes changed during read")
        return sorted(vector_ids), digest
    except ChromaCustodyError:
        raise
    except (sqlite3.Error, OSError, UnicodeError, ValueError, TypeError):
        # Driver exceptions can include private paths and SQL schema/data.
        raise ChromaCustodyError("Chroma catalog read-only query unavailable") from None


def _hash_index(member: Path, *, deadline: float) -> tuple[str, int]:
    """Constant-RAM SHA-256 on an O_NOFOLLOW fd, with physical deadline."""
    original = _private(member, directory=False)
    digest = hashlib.sha256()
    counted = 0
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(member, flags), "rb", buffering=0) as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                original[0], original[1], original[3]
            ):
                raise ChromaCustodyError("Chroma HNSW opened file identity changed")
            while True:
                if time.monotonic() > deadline:
                    raise ChromaCustodyError("Chroma HNSW hash deadline exceeded")
                chunk = stream.read(4 * 1024 * 1024)
                if not chunk:
                    break
                counted += len(chunk)
                if counted > _MAX_INDEX_FILE:
                    raise ChromaCustodyError("Chroma HNSW source file exceeded budget")
                digest.update(chunk)
            after_open = os.fstat(stream.fileno())
            if (after_open.st_dev, after_open.st_ino,
                    after_open.st_size, after_open.st_mtime_ns,
                    after_open.st_ctime_ns) != (
                    original[0], original[1], original[3],
                    original[4], original[5]):
                raise ChromaCustodyError("Chroma HNSW file modified during read")
        if counted != original[3] or _private(member, directory=False) != original:
            raise ChromaCustodyError("Chroma HNSW hash identity not stable")
        return digest.hexdigest(), counted
    except ChromaCustodyError:
        raise
    except OSError:
        raise ChromaCustodyError("Chroma HNSW file not readable") from None


def _index_files(root: Path, uuid: str, *, deadline: float) -> tuple[int, bytes]:
    folder = root / uuid
    before = _private(folder, directory=True)
    try:
        listed = {x.name for x in folder.iterdir()}
    except OSError:
        raise ChromaCustodyError("Chroma HNSW segment directory unreadable") from None
    if listed != _INDEX:
        raise ChromaCustodyError("Chroma HNSW binary set incomplete or unrecognized")
    total = 0
    digest = hashlib.sha256(b"skeleton.chroma.hnsw-index-files.v1\x00")
    for filename in sorted(_INDEX):
        if time.monotonic() > deadline:
            raise ChromaCustodyError("Chroma HNSW file audit deadline exceeded")
        member = folder / filename
        start = _private(member, directory=False)
        content_sha, content_size = _hash_index(
            member, deadline=deadline,
        )
        end = _private(member, directory=False)
        if start != end or content_size != start[3]:
            raise ChromaCustodyError("Chroma HNSW binary changed while hashing")
        if filename == "header.bin" and not 16 <= content_size <= 4096:
            raise ChromaCustodyError("Chroma HNSW header outside plausible range")
        if filename == "index_metadata.pickle" and content_size > 256 * 1024 ** 2:
            raise ChromaCustodyError("Chroma index metadata outside bounded range")
        # Do not deserialize the .pickle file. Its bytes are only hashed.
        total += content_size
        if total > _MAX_TOTAL_BYTES:
            raise ChromaCustodyError("Chroma HNSW inventory exceeds budget")
        digest.update(filename.encode("ascii") + b"\x00")
        digest.update(content_size.to_bytes(8, "big"))
        digest.update(bytes.fromhex(content_sha))
    if _private(folder, directory=True) != before:
        raise ChromaCustodyError("Chroma HNSW directory changed during hashing")
    if {p.name for p in folder.iterdir()} != _INDEX:
        raise ChromaCustodyError("Chroma HNSW files changed during hashing")
    return total, digest.digest()


def inspect_restored_chroma(
    source: Path, destination: Path, *,
    expected_receipt_sha256: str,
) -> dict[str, object]:
    """Qualify only physical envelope and catalog/index identity consistency."""
    try:
        verified = rehydrate.verify_rehydration(
            source, destination,
            expected_receipt_sha256=expected_receipt_sha256,
        )
    except Exception:
        raise ChromaCustodyError(
            "independent offline Chroma byte-restore receipt unavailable"
        ) from None
    if (
        verified.get("roles") not in (
            ["backend_data", "chroma_data", "mongo_config", "mongo_data", "skeleton_data"],
        )
        or verified.get("database_process_started") is not False
        or verified.get("docker_daemon_used") is not False
        or verified.get("cross_store_snapshot_atomic") is not False
        or verified.get("application_restore_qualified") is not False
    ):
        raise ChromaCustodyError(
            "Chroma restore prerequisite does not establish known cold role custody"
        )
    root = rehydrate.cold._private_root(destination, must_exist=True)
    chroma = root / "chroma_data"
    _private(chroma, directory=True)
    sqlite_path = chroma / _SQLITE
    deadline = time.monotonic() + _MAX_SECONDS
    ids, catalog_sha = _catalog(sqlite_path, deadline=deadline)
    try:
        children = {item.name for item in chroma.iterdir()}
    except OSError:
        raise ChromaCustodyError("restored Chroma root unavailable") from None
    if (
        _SQLITE not in children
        or children != {_SQLITE, *ids}
    ):
        raise ChromaCustodyError(
            "Chroma catalog and physical persistent vector segment inventory differ"
        )
    if not ids:
        return {
            "schema": SCHEMA,
            "status": "chroma_metadata_present_no_persistent_hnsw_segments",
            "persistent_vector_segments": 0,
            "all_index_files_present_and_hashed": False,
            "hnsw_graph_load_qualified": False,
            "chroma_logical_replay_qualified": False,
            "database_documents_read": False,
            "source_archive_modified": False,
            "restored_bytes_modified": False,
            "mongo_consistency_verified": False,
            "cross_store_snapshot_atomic": False,
            "application_restore_qualified": False,
            "release_authorized": False,
        }
    digest = hashlib.sha256(b"skeleton.chroma.segment-custody.v1\x00")
    digest.update(bytes.fromhex(catalog_sha))
    total = 0
    for uuid in ids:
        if time.monotonic() > deadline:
            raise ChromaCustodyError("Chroma index snapshot audit deadline exceeded")
        size, sha = _index_files(chroma, uuid, deadline=deadline)
        total += size
        if total > _MAX_TOTAL_BYTES:
            raise ChromaCustodyError("Chroma total binary index exceeds bounded budget")
        digest.update(uuid.encode("ascii") + b"\x00" + sha)
    sqlite_gate._require_no_sidecar(sqlite_path)
    current_ids, last_catalog_sha = _catalog(sqlite_path, deadline=deadline)
    if (
        ids != current_ids or catalog_sha != last_catalog_sha
        or {item.name for item in chroma.iterdir()} != {_SQLITE, *ids}
    ):
        raise ChromaCustodyError("Chroma index/catalog identity changed during audit")
    return {
        "schema": SCHEMA,
        "status": "read_only_legacy_hnsw_file_custody_not_chroma_recovery",
        "persistent_vector_segments": len(ids),
        "hashed_index_files": len(ids) * len(_INDEX),
        "total_binary_index_bytes": total,
        "catalog_and_segment_file_identity_verified": True,
        "all_index_files_present_and_hashed": True,
        "aggregate_fingerprint_sha256": digest.hexdigest(),
        "pickle_deserialized": False,
        "hnsw_graph_load_qualified": False,
        "chroma_logical_replay_qualified": False,
        "database_documents_read": False,
        "source_archive_modified": False,
        "restored_bytes_modified": False,
        "mongo_consistency_verified": False,
        "cross_store_snapshot_atomic": False,
        "application_restore_qualified": False,
        "protected_jeeves_chat_qualified": False,
        "release_authorized": False,
    }


__all__ = [
    "ChromaCustodyError", "inspect_restored_chroma",
]
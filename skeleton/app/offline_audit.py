"""Deep, read-only semantic integrity inspection for standalone AI data.

An SQLite integrity_check only verifies the physical database; it cannot
detect internally inconsistent conversation digests, dangling document FTS
rows, invalid message order or corrupt job state. This checker validates
those application invariants without executing AI, accessing network or
creating/changing any tables.
"""
from __future__ import annotations

import hashlib
from contextlib import closing
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from typing import Any

from .offline_snapshot import KINDS, MAX_DATABASE_BYTES
from .offline_sqlite_safety import check_sqlite_companion_paths, UnsafeOfflineSqlitePath


AUDIT_SCHEMA = "skeleton.app.offline_state_audit.v1"
MAX_ROWS = 50000
MAX_AUDIT_BYTES = 192 * 1024 * 1024
_HEX = re.compile(r"^[0-9a-f]{64}$")
_JOB = re.compile(r"^[0-9a-f]{32}$")


class OfflineAuditError(RuntimeError):
    """A local SQLite data domain fails semantic or structural verification."""


def _admit(source: str | Path) -> Path:
    path = Path(os.path.abspath(Path(source).expanduser()))
    if path.is_symlink() or not path.is_file():
        raise OfflineAuditError("audit source must be a real local SQLite database")
    try:
        check_sqlite_companion_paths(path)
    except UnsafeOfflineSqlitePath as exc:
        raise OfflineAuditError(str(exc)) from exc
    if path.stat().st_size > MAX_DATABASE_BYTES:
        raise OfflineAuditError("audit source exceeds maximum database size")
    return path


def _rows(conn: sqlite3.Connection, query: str) -> list[tuple[Any, ...]]:
    # Fetch incrementally. Malicious but structurally valid SQLite databases
    # must not allocate an unbounded table of large text/blob values in RAM.
    records: list[tuple[Any, ...]] = []
    total_bytes = 0
    cursor = conn.execute(query + " LIMIT ?", (MAX_ROWS + 1,))
    for row in cursor:
        if len(records) >= MAX_ROWS:
            raise OfflineAuditError("local database exceeds audit row budget")
        for cell in row:
            if isinstance(cell, str):
                total_bytes += len(cell.encode("utf-8", errors="surrogatepass"))
            elif isinstance(cell, bytes):
                total_bytes += len(cell)
        if total_bytes > MAX_AUDIT_BYTES:
            raise OfflineAuditError("local database exceeds semantic audit memory budget")
        records.append(row)
    return records


def _workspace(conn: sqlite3.Connection) -> dict[str, int]:
    from .offline_workspace import _session_id, _load_snapshot

    rows = _rows(
        conn,
        "SELECT session_id, model_digest, revision, history_json, history_sha256 "
        "FROM offline_conversations ORDER BY session_id",
    )
    turns = 0
    for sid, model, revision, history_json, digest in rows:
        try:
            _session_id(sid)
            if not isinstance(model, str) or not _HEX.fullmatch(model):
                raise OfflineAuditError("workspace model hash is invalid")
            if type(revision) is not int or revision < 0:
                raise OfflineAuditError("workspace revision is invalid")
            messages = _load_snapshot(history_json, digest)
        except (ValueError, TypeError, RuntimeError) as exc:
            raise OfflineAuditError("workspace contains malformed conversation") from exc
        turns += len(messages) // 2
    return {"conversations": len(rows), "complete_turns": turns}


def _library(conn: sqlite3.Connection) -> dict[str, int]:
    from .offline_library import MAX_DOCUMENT_BYTES

    records = _rows(
        conn,
        "SELECT id, root, relative_path, sha256, body, size_bytes "
        "FROM offline_documents ORDER BY id",
    )
    fts = _rows(
        conn,
        "SELECT rowid, body FROM offline_document_fts ORDER BY rowid",
    )
    by_id = {rowid: body for rowid, body in fts}
    if len(by_id) != len(fts) or len(fts) != len(records):
        raise OfflineAuditError("FTS5 document count or identity does not match source rows")
    total_bytes = 0
    for docid, root, relative, digest, body, size in records:
        if (
            type(docid) is not int or docid not in by_id
            or not isinstance(root, str) or not root
            or not isinstance(relative, str) or not relative
            or relative.startswith("/") or "\x00" in relative
            or ".." in Path(relative).parts
            or not isinstance(digest, str) or not _HEX.fullmatch(digest)
            or not isinstance(body, str)
            or type(size) is not int or size < 0 or size > MAX_DOCUMENT_BYTES
        ):
            raise OfflineAuditError("local document index row has invalid fields")
        raw = body.encode("utf-8")
        if (
            len(raw) != size
            or hashlib.sha256(raw).hexdigest() != digest
            or by_id[docid] != body
        ):
            raise OfflineAuditError("local document or FTS5 projection failed integrity validation")
        total_bytes += size
    return {"documents": len(records), "indexed_bytes": total_bytes}


def _queue(conn: sqlite3.Connection) -> dict[str, int]:
    from .offline_index_queue import MAX_ATTEMPTS

    rows = _rows(
        conn,
        "SELECT job_id,state,source,library,attempts,created_at,updated_at,"
        "next_due_at,lease_token,lease_until,last_error,result_json "
        "FROM offline_index_jobs ORDER BY job_id",
    )
    pending = 0
    active: set[tuple[str, str]] = set()
    allowed = {"queued", "running", "completed", "failed", "cancelled"}
    for row in rows:
        job, state, source, library, attempts, created, updated, due, token, until, error, result = row
        if (
            not isinstance(job, str) or _JOB.fullmatch(job) is None
            or state not in allowed
            or not isinstance(source, str) or not source
            or not isinstance(library, str) or not library
            or type(attempts) is not int or not 0 <= attempts <= MAX_ATTEMPTS
            or any(type(t) not in (int, float) or not math.isfinite(t) for t in (created, updated, due))
            or (error is not None and not isinstance(error, str))
        ):
            raise OfflineAuditError("local indexing job has invalid state fields")
        if state in ("queued", "running"):
            pending += 1
            key = (source, library)
            if key in active:
                raise OfflineAuditError("duplicate live offline indexing job for same source")
            active.add(key)
        if state == "running":
            if (
                not isinstance(token, str) or _JOB.fullmatch(token) is None
                or type(until) not in (int, float) or not math.isfinite(until)
                or attempts == 0
            ):
                raise OfflineAuditError("running indexing job has invalid lease")
        elif token is not None or until is not None:
            raise OfflineAuditError("non-running indexing job retained active lease")
        if result is not None:
            if state != "completed":
                raise OfflineAuditError("non-completed indexing job has completion result")
            try:
                parsed = json.loads(
                    result,
                    parse_constant=lambda _value: (_ for _ in ()).throw(
                        ValueError("non-finite job receipt value")
                    ),
                )
            except (ValueError, TypeError) as exc:
                raise OfflineAuditError("invalid offline indexing job result") from exc
            required = ("indexed_files", "updated_files", "removed_files", "indexed_bytes")
            if (
                not isinstance(parsed, dict)
                or not all(field in parsed for field in required)
                or any(type(parsed[field]) is not int or parsed[field] < 0
                       for field in required)
                or parsed["updated_files"] > parsed["indexed_files"]
            ):
                raise OfflineAuditError("completed indexing job has invalid result schema")
        elif state == "completed":
            raise OfflineAuditError("completed indexing job is missing its result")
    return {"jobs": len(rows), "pending_jobs": pending}


def audit_database(path: str | Path, kind: str) -> dict[str, Any]:
    """Verify SQLite storage and its semantic owner-specific invariants.

    The caller must stop mutating writers to use the report as a stable
    baseline; a read transaction gives a consistent single-file snapshot.
    """
    if kind not in KINDS:
        raise OfflineAuditError("unknown offline audit data domain")
    source = _admit(path)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=10)) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            if conn.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise OfflineAuditError("SQLite integrity check failed")
            table = KINDS[kind][1]
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone():
                raise OfflineAuditError("offline database is missing required schema")
            details = {
                "workspace": _workspace,
                "library": _library,
                "queue": _queue,
            }[kind](conn)
    except sqlite3.Error as exc:
        raise OfflineAuditError("cannot inspect offline SQLite database") from exc
    return {
        "schema_version": AUDIT_SCHEMA,
        "kind": kind,
        "ok": True,
        "inspected_file": str(source),
        **details,
    }


__all__ = ["AUDIT_SCHEMA", "OfflineAuditError", "audit_database"]

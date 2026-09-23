"""Durable reference repository for canonical memory authority.

This SQLite implementation is intentionally small and strict. It proves the
repository contract: restart durability, tenant/namespace isolation,
idempotent writes, optimistic version updates, immutable provenance, and
tombstone semantics. Derived vector/graph indexes may rebuild from this state.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from typing import Iterable
from uuid import uuid4

from skeleton.contracts.memory_record import (
    MemoryKind,
    MemoryRecord,
    MemoryState,
    MemoryWriteProposal,
)


class MemoryRepositoryError(RuntimeError):
    """Base durable memory repository error."""


class MemoryNotFound(MemoryRepositoryError):
    """Requested memory does not exist in the caller's authority scope."""


class MemoryConflict(MemoryRepositoryError):
    """Idempotency/version/ownership conflict."""


def _utc(value: datetime | None = None) -> datetime:
    instant = datetime.now(timezone.utc) if value is None else value
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise MemoryRepositoryError("timestamps must be timezone-aware")
    return instant.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else _utc(value).isoformat()


def _parse_time(raw: object, field: str) -> datetime | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise MemoryRepositoryError(f"{field} must be ISO-8601 text")
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise MemoryRepositoryError(f"{field} is invalid") from exc
    return _utc(value)


def _refs(values: Iterable[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _parse_refs(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, str):
        raise MemoryRepositoryError("provenance_refs_json must be JSON text")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MemoryRepositoryError("provenance_refs_json is invalid") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise MemoryRepositoryError("provenance_refs_json must contain strings")
    return tuple(value)


def _proposal_digest(proposal: MemoryWriteProposal) -> str:
    payload = {
        "tenant_id": proposal.tenant_id,
        "namespace": proposal.namespace,
        "subject_id": proposal.subject_id,
        "kind": proposal.kind.value,
        "idempotency_key": proposal.idempotency_key,
        "payload_digest": proposal.payload_digest,
        "source_operation_id": proposal.source_operation_id,
        "target_memory_id": proposal.target_memory_id,
        "expected_version": proposal.expected_version,
        "expires_at": _iso(proposal.expires_at),
        "data_class": proposal.data_class,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _record_json(record: MemoryRecord) -> str:
    return json.dumps(
        record.as_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _record_from_json(raw: object) -> MemoryRecord:
    if not isinstance(raw, str):
        raise MemoryRepositoryError("idempotency result must be JSON text")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MemoryRepositoryError("idempotency result is invalid JSON") from exc
    if not isinstance(data, dict):
        raise MemoryRepositoryError("idempotency result must be an object")
    return MemoryRecord(
        memory_id=data["memory_id"],
        tenant_id=data["tenant_id"],
        namespace=data["namespace"],
        subject_id=data["subject_id"],
        kind=MemoryKind(data["kind"]),
        version=int(data["version"]),
        created_at=_parse_time(data["created_at"], "created_at"),
        updated_at=_parse_time(data["updated_at"], "updated_at"),
        idempotency_key=data["idempotency_key"],
        payload_digest=data["payload_digest"],
        content=data.get("content"),
        content_ref=data.get("content_ref"),
        provenance_refs=tuple(data.get("provenance_refs") or ()),
        source_operation_id=data.get("source_operation_id"),
        expires_at=_parse_time(data.get("expires_at"), "expires_at"),
        state=MemoryState(data["state"]),
        data_class=data["data_class"],
        schema_version=int(data.get("schema_version", 1)),
    )


class SQLiteMemoryRepository:
    """Transactional canonical memory store with explicit authority scope."""

    def __init__(self, path: str | Path = ":memory:", *, repository_namespace: str = "memory") -> None:
        namespace = str(repository_namespace).strip()
        if not namespace:
            raise ValueError("repository_namespace must not be empty")
        self.repository_namespace = namespace
        self._connection = sqlite3.connect(
            str(path),
            check_same_thread=False,
            isolation_level=None,
            timeout=5.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS canonical_memory (
                    repository_namespace TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    content TEXT,
                    content_ref TEXT,
                    provenance_refs_json TEXT NOT NULL,
                    source_operation_id TEXT,
                    expires_at TEXT,
                    state TEXT NOT NULL,
                    data_class TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    PRIMARY KEY(repository_namespace, memory_id),
                    UNIQUE(repository_namespace, tenant_id, namespace, idempotency_key)
                );

                CREATE INDEX IF NOT EXISTS idx_canonical_memory_subject
                ON canonical_memory(
                    repository_namespace, tenant_id, namespace, subject_id, state, updated_at
                );

                CREATE TABLE IF NOT EXISTS canonical_memory_idempotency (
                    repository_namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    PRIMARY KEY(
                        repository_namespace, tenant_id, namespace, idempotency_key
                    )
                );
                """
            )

    @staticmethod
    def _record(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            memory_id=row["memory_id"],
            tenant_id=row["tenant_id"],
            namespace=row["namespace"],
            subject_id=row["subject_id"],
            kind=MemoryKind(row["kind"]),
            version=int(row["version"]),
            created_at=_parse_time(row["created_at"], "created_at"),
            updated_at=_parse_time(row["updated_at"], "updated_at"),
            idempotency_key=row["idempotency_key"],
            payload_digest=row["payload_digest"],
            content=row["content"],
            content_ref=row["content_ref"],
            provenance_refs=_parse_refs(row["provenance_refs_json"]),
            source_operation_id=row["source_operation_id"],
            expires_at=_parse_time(row["expires_at"], "expires_at"),
            state=MemoryState(row["state"]),
            data_class=row["data_class"],
            schema_version=int(row["schema_version"]),
        )

    def _find_idempotency(self, proposal: MemoryWriteProposal) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT * FROM canonical_memory_idempotency
            WHERE repository_namespace = ?
              AND tenant_id = ?
              AND namespace = ?
              AND idempotency_key = ?
            """,
            (
                self.repository_namespace,
                proposal.tenant_id,
                proposal.namespace,
                proposal.idempotency_key,
            ),
        ).fetchone()

    def _record_idempotency(
        self,
        proposal: MemoryWriteProposal,
        record: MemoryRecord,
        *,
        committed_at: datetime,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO canonical_memory_idempotency (
                repository_namespace, tenant_id, namespace, idempotency_key,
                request_digest, result_json, committed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.repository_namespace,
                proposal.tenant_id,
                proposal.namespace,
                proposal.idempotency_key,
                _proposal_digest(proposal),
                _record_json(record),
                _iso(committed_at),
            ),
        )

    def _find_memory(
        self,
        memory_id: str,
        *,
        tenant_id: str,
        namespace: str,
    ) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT * FROM canonical_memory
            WHERE repository_namespace = ?
              AND memory_id = ?
              AND tenant_id = ?
              AND namespace = ?
            """,
            (self.repository_namespace, memory_id, tenant_id, namespace),
        ).fetchone()

    def commit(
        self,
        proposal: MemoryWriteProposal,
        *,
        now: datetime | None = None,
    ) -> MemoryRecord:
        if not isinstance(proposal, MemoryWriteProposal):
            raise TypeError("proposal must be MemoryWriteProposal")
        instant = _utc(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                replay = self._find_idempotency(proposal)
                if replay is not None:
                    if str(replay["request_digest"]) != _proposal_digest(proposal):
                        raise MemoryConflict(
                            "idempotency_key replayed with different memory write intent"
                        )
                    record = _record_from_json(replay["result_json"])
                    self._connection.execute("COMMIT")
                    return record

                if proposal.target_memory_id is None:
                    record = MemoryRecord(
                        memory_id=str(uuid4()),
                        tenant_id=proposal.tenant_id,
                        namespace=proposal.namespace,
                        subject_id=proposal.subject_id,
                        kind=proposal.kind,
                        version=1,
                        created_at=instant,
                        updated_at=instant,
                        idempotency_key=proposal.idempotency_key,
                        payload_digest=proposal.payload_digest,
                        content=proposal.content,
                        content_ref=proposal.content_ref,
                        provenance_refs=proposal.provenance_refs,
                        source_operation_id=proposal.source_operation_id,
                        expires_at=proposal.expires_at,
                        state=MemoryState.ACTIVE,
                        data_class=proposal.data_class,
                    )
                    self._connection.execute(
                        """
                        INSERT INTO canonical_memory (
                            repository_namespace, memory_id, tenant_id, namespace,
                            subject_id, kind, version, created_at, updated_at,
                            idempotency_key, payload_digest, content, content_ref,
                            provenance_refs_json, source_operation_id, expires_at,
                            state, data_class, schema_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            self.repository_namespace,
                            record.memory_id,
                            record.tenant_id,
                            record.namespace,
                            record.subject_id,
                            record.kind.value,
                            record.version,
                            _iso(record.created_at),
                            _iso(record.updated_at),
                            record.idempotency_key,
                            record.payload_digest,
                            record.content,
                            record.content_ref,
                            _refs(record.provenance_refs),
                            record.source_operation_id,
                            _iso(record.expires_at),
                            record.state.value,
                            record.data_class,
                            record.schema_version,
                        ),
                    )
                else:
                    row = self._find_memory(
                        proposal.target_memory_id,
                        tenant_id=proposal.tenant_id,
                        namespace=proposal.namespace,
                    )
                    if row is None:
                        raise MemoryNotFound("target memory not found in authority scope")
                    current = self._record(row)
                    if current.state is not MemoryState.ACTIVE:
                        raise MemoryConflict("tombstoned memory is not writable")
                    if proposal.expected_version is None:
                        raise MemoryConflict("update requires expected_version")
                    if current.version != proposal.expected_version:
                        raise MemoryConflict("memory version conflict")
                    if current.subject_id != proposal.subject_id:
                        raise MemoryConflict("memory subject cannot change")
                    record = MemoryRecord(
                        memory_id=current.memory_id,
                        tenant_id=current.tenant_id,
                        namespace=current.namespace,
                        subject_id=current.subject_id,
                        kind=proposal.kind,
                        version=current.version + 1,
                        created_at=current.created_at,
                        updated_at=instant,
                        idempotency_key=proposal.idempotency_key,
                        payload_digest=proposal.payload_digest,
                        content=proposal.content,
                        content_ref=proposal.content_ref,
                        provenance_refs=proposal.provenance_refs,
                        source_operation_id=proposal.source_operation_id,
                        expires_at=proposal.expires_at,
                        state=MemoryState.ACTIVE,
                        data_class=proposal.data_class,
                    )
                    self._connection.execute(
                        """
                        UPDATE canonical_memory
                        SET kind = ?, version = ?, updated_at = ?,
                            idempotency_key = ?, payload_digest = ?,
                            content = ?, content_ref = ?, provenance_refs_json = ?,
                            source_operation_id = ?, expires_at = ?,
                            data_class = ?, schema_version = ?
                        WHERE repository_namespace = ? AND memory_id = ?
                        """,
                        (
                            record.kind.value,
                            record.version,
                            _iso(record.updated_at),
                            record.idempotency_key,
                            record.payload_digest,
                            record.content,
                            record.content_ref,
                            _refs(record.provenance_refs),
                            record.source_operation_id,
                            _iso(record.expires_at),
                            record.data_class,
                            record.schema_version,
                            self.repository_namespace,
                            record.memory_id,
                        ),
                    )
                self._record_idempotency(
                    proposal,
                    record,
                    committed_at=instant,
                )
                self._connection.execute("COMMIT")
                return record
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def get(
        self,
        memory_id: str,
        *,
        tenant_id: str,
        namespace: str,
        include_tombstoned: bool = False,
    ) -> MemoryRecord:
        with self._lock:
            row = self._find_memory(
                str(memory_id),
                tenant_id=str(tenant_id),
                namespace=str(namespace),
            )
            if row is None:
                raise MemoryNotFound("memory not found in authority scope")
            record = self._record(row)
            if record.state is MemoryState.TOMBSTONED and not include_tombstoned:
                raise MemoryNotFound("memory not found in authority scope")
            return record

    def list_subject(
        self,
        *,
        tenant_id: str,
        namespace: str,
        subject_id: str,
        include_tombstoned: bool = False,
    ) -> tuple[MemoryRecord, ...]:
        query = """
            SELECT * FROM canonical_memory
            WHERE repository_namespace = ?
              AND tenant_id = ?
              AND namespace = ?
              AND subject_id = ?
        """
        params: list[object] = [
            self.repository_namespace,
            str(tenant_id),
            str(namespace),
            str(subject_id),
        ]
        if not include_tombstoned:
            query += " AND state = ?"
            params.append(MemoryState.ACTIVE.value)
        query += " ORDER BY updated_at ASC, memory_id ASC"
        with self._lock:
            return tuple(self._record(row) for row in self._connection.execute(query, params))

    def tombstone(
        self,
        memory_id: str,
        *,
        tenant_id: str,
        namespace: str,
        expected_version: int,
        now: datetime | None = None,
    ) -> MemoryRecord:
        instant = _utc(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._find_memory(
                    str(memory_id),
                    tenant_id=str(tenant_id),
                    namespace=str(namespace),
                )
                if row is None:
                    raise MemoryNotFound("memory not found in authority scope")
                current = self._record(row)
                if current.version != expected_version:
                    raise MemoryConflict("memory version conflict")
                if current.state is MemoryState.TOMBSTONED:
                    self._connection.execute("COMMIT")
                    return current
                self._connection.execute(
                    """
                    UPDATE canonical_memory
                    SET version = ?, updated_at = ?, state = ?
                    WHERE repository_namespace = ? AND memory_id = ?
                    """,
                    (
                        current.version + 1,
                        _iso(instant),
                        MemoryState.TOMBSTONED.value,
                        self.repository_namespace,
                        current.memory_id,
                    ),
                )
                row = self._find_memory(
                    current.memory_id,
                    tenant_id=current.tenant_id,
                    namespace=current.namespace,
                )
                assert row is not None
                self._connection.execute("COMMIT")
                return self._record(row)
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            self._connection.close()


__all__ = [
    "MemoryConflict",
    "MemoryNotFound",
    "MemoryRepositoryError",
    "SQLiteMemoryRepository",
]

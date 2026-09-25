"""Durable reference repository for canonical memory authority.

This SQLite implementation is intentionally small and strict. It proves the
repository contract: restart durability, tenant/namespace isolation,
idempotent writes, optimistic version updates, immutable provenance, and
tombstone semantics. Derived vector/graph indexes may rebuild from this state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Iterable
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


_REVISION_MUTATIONS = frozenset({"create", "update", "tombstone", "expire"})
_PROJECTION_ACTIONS = frozenset({"upsert", "delete"})


@dataclass(frozen=True, slots=True)
class MemoryRevision:
    """Immutable predecessor-linked snapshot of one canonical memory version."""

    memory_id: str
    tenant_id: str
    namespace: str
    version: int
    predecessor_version: int | None
    mutation: str
    committed_at: datetime
    record: MemoryRecord

    def __post_init__(self) -> None:
        if self.record.memory_id != self.memory_id:
            raise MemoryRepositoryError("memory revision record identity mismatch")
        if self.record.tenant_id != self.tenant_id or self.record.namespace != self.namespace:
            raise MemoryRepositoryError("memory revision authority scope mismatch")
        if self.record.version != self.version:
            raise MemoryRepositoryError("memory revision version mismatch")
        if self.mutation not in _REVISION_MUTATIONS:
            raise MemoryRepositoryError("memory revision mutation is invalid")
        _utc(self.committed_at)
        if self.version == 1:
            if self.predecessor_version is not None:
                raise MemoryRepositoryError("initial memory revision cannot have predecessor")
        elif self.predecessor_version != self.version - 1:
            raise MemoryRepositoryError("memory revision predecessor must be exact previous version")


@dataclass(frozen=True, slots=True)
class MemoryProjectionEvent:
    """Durable derived-store work emitted from canonical memory mutations."""

    event_id: str
    tenant_id: str
    namespace: str
    memory_id: str
    memory_version: int
    action: str
    created_at: datetime
    record: MemoryRecord
    published_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id:
            raise MemoryRepositoryError("projection event id must be non-empty")
        if self.action not in _PROJECTION_ACTIONS:
            raise MemoryRepositoryError("projection action is invalid")
        if self.record.memory_id != self.memory_id or self.record.version != self.memory_version:
            raise MemoryRepositoryError("projection event record identity/version mismatch")
        if self.record.tenant_id != self.tenant_id or self.record.namespace != self.namespace:
            raise MemoryRepositoryError("projection event authority scope mismatch")
        _utc(self.created_at)
        if self.published_at is not None:
            published = _utc(self.published_at)
            if published < _utc(self.created_at):
                raise MemoryRepositoryError("projection publish time cannot precede creation")


def _projection_event_id(record: MemoryRecord, action: str) -> str:
    if action not in _PROJECTION_ACTIONS:
        raise MemoryRepositoryError("projection action is invalid")
    payload = f"{record.memory_id}:{record.version}:{action}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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

                CREATE TABLE IF NOT EXISTS canonical_memory_revisions (
                    repository_namespace TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    predecessor_version INTEGER,
                    mutation TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    PRIMARY KEY(repository_namespace, memory_id, version)
                );

                CREATE INDEX IF NOT EXISTS idx_canonical_memory_revisions_scope
                ON canonical_memory_revisions(
                    repository_namespace, tenant_id, namespace, memory_id, version
                );

                CREATE TABLE IF NOT EXISTS canonical_memory_projection_outbox (
                    repository_namespace TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    memory_version INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    published_at TEXT,
                    PRIMARY KEY(repository_namespace, event_id),
                    UNIQUE(
                        repository_namespace, memory_id, memory_version, action
                    )
                );

                CREATE INDEX IF NOT EXISTS idx_canonical_memory_projection_pending
                ON canonical_memory_projection_outbox(
                    repository_namespace, published_at, created_at, memory_id, memory_version
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

    def _record_revision(
        self,
        record: MemoryRecord,
        *,
        mutation: str,
        predecessor_version: int | None,
        committed_at: datetime,
    ) -> None:
        revision = MemoryRevision(
            memory_id=record.memory_id,
            tenant_id=record.tenant_id,
            namespace=record.namespace,
            version=record.version,
            predecessor_version=predecessor_version,
            mutation=mutation,
            committed_at=_utc(committed_at),
            record=record,
        )
        self._connection.execute(
            """
            INSERT INTO canonical_memory_revisions (
                repository_namespace, memory_id, tenant_id, namespace, version,
                predecessor_version, mutation, committed_at, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.repository_namespace,
                revision.memory_id,
                revision.tenant_id,
                revision.namespace,
                revision.version,
                revision.predecessor_version,
                revision.mutation,
                _iso(revision.committed_at),
                _record_json(revision.record),
            ),
        )

    def _record_projection_event(
        self,
        record: MemoryRecord,
        *,
        action: str,
        created_at: datetime,
    ) -> None:
        event = MemoryProjectionEvent(
            event_id=_projection_event_id(record, action),
            tenant_id=record.tenant_id,
            namespace=record.namespace,
            memory_id=record.memory_id,
            memory_version=record.version,
            action=action,
            created_at=_utc(created_at),
            record=record,
        )
        self._connection.execute(
            """
            INSERT INTO canonical_memory_projection_outbox (
                repository_namespace, event_id, tenant_id, namespace,
                memory_id, memory_version, action, record_json,
                created_at, published_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                self.repository_namespace,
                event.event_id,
                event.tenant_id,
                event.namespace,
                event.memory_id,
                event.memory_version,
                event.action,
                _record_json(event.record),
                _iso(event.created_at),
            ),
        )

    @staticmethod
    def _revision(row: sqlite3.Row) -> MemoryRevision:
        record = _record_from_json(row["record_json"])
        return MemoryRevision(
            memory_id=row["memory_id"],
            tenant_id=row["tenant_id"],
            namespace=row["namespace"],
            version=int(row["version"]),
            predecessor_version=(
                None
                if row["predecessor_version"] is None
                else int(row["predecessor_version"])
            ),
            mutation=row["mutation"],
            committed_at=_parse_time(row["committed_at"], "committed_at"),
            record=record,
        )

    @staticmethod
    def _projection_event(row: sqlite3.Row) -> MemoryProjectionEvent:
        return MemoryProjectionEvent(
            event_id=row["event_id"],
            tenant_id=row["tenant_id"],
            namespace=row["namespace"],
            memory_id=row["memory_id"],
            memory_version=int(row["memory_version"]),
            action=row["action"],
            created_at=_parse_time(row["created_at"], "created_at"),
            record=_record_from_json(row["record_json"]),
            published_at=_parse_time(row["published_at"], "published_at"),
        )

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
                    mutation = "create"
                    predecessor_version = None
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
                    mutation = "update"
                    predecessor_version = current.version
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
                self._record_revision(
                    record,
                    mutation=mutation,
                    predecessor_version=predecessor_version,
                    committed_at=instant,
                )
                self._record_projection_event(
                    record,
                    action="upsert",
                    created_at=instant,
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

    def history(
        self,
        memory_id: str,
        *,
        tenant_id: str,
        namespace: str,
    ) -> tuple[MemoryRevision, ...]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM canonical_memory_revisions
                WHERE repository_namespace = ?
                  AND memory_id = ?
                  AND tenant_id = ?
                  AND namespace = ?
                ORDER BY version ASC
                """,
                (
                    self.repository_namespace,
                    str(memory_id),
                    str(tenant_id),
                    str(namespace),
                ),
            ).fetchall()
            return tuple(self._revision(row) for row in rows)

    def pending_projection_events(
        self,
        *,
        limit: int = 100,
    ) -> tuple[MemoryProjectionEvent, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("projection event limit must be an integer")
        if limit < 1:
            raise ValueError("projection event limit must be positive")
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM canonical_memory_projection_outbox
                WHERE repository_namespace = ?
                  AND published_at IS NULL
                ORDER BY created_at ASC, memory_id ASC, memory_version ASC, event_id ASC
                LIMIT ?
                """,
                (self.repository_namespace, limit),
            ).fetchall()
            return tuple(self._projection_event(row) for row in rows)

    def mark_projection_published(
        self,
        event_id: str,
        *,
        now: datetime | None = None,
    ) -> MemoryProjectionEvent:
        event_key = str(event_id).strip()
        if not event_key:
            raise ValueError("projection event id must not be empty")
        instant = _utc(now)
        with self._lock:
            self._connection.execute(
                """
                UPDATE canonical_memory_projection_outbox
                SET published_at = COALESCE(published_at, ?)
                WHERE repository_namespace = ? AND event_id = ?
                """,
                (_iso(instant), self.repository_namespace, event_key),
            )
            row = self._connection.execute(
                """
                SELECT * FROM canonical_memory_projection_outbox
                WHERE repository_namespace = ? AND event_id = ?
                """,
                (self.repository_namespace, event_key),
            ).fetchone()
            if row is None:
                raise MemoryNotFound("projection event not found")
            return self._projection_event(row)

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
                if current.state is MemoryState.TOMBSTONED:
                    if expected_version not in {current.version, current.version - 1}:
                        raise MemoryConflict("memory version conflict")
                    self._connection.execute("COMMIT")
                    return current
                if current.version != expected_version:
                    raise MemoryConflict("memory version conflict")
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
                record = self._record(row)
                self._record_revision(
                    record,
                    mutation="tombstone",
                    predecessor_version=current.version,
                    committed_at=instant,
                )
                self._record_projection_event(
                    record,
                    action="delete",
                    created_at=instant,
                )
                self._connection.execute("COMMIT")
                return record
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def expire_due(
        self,
        *,
        tenant_id: str,
        namespace: str,
        now: datetime | None = None,
    ) -> tuple[MemoryRecord, ...]:
        """Tombstone active records whose canonical expiry has elapsed."""

        instant = _utc(now)
        expired: list[MemoryRecord] = []
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                rows = self._connection.execute(
                    """
                    SELECT * FROM canonical_memory
                    WHERE repository_namespace = ?
                      AND tenant_id = ?
                      AND namespace = ?
                      AND state = ?
                      AND expires_at IS NOT NULL
                    ORDER BY expires_at ASC, memory_id ASC
                    """,
                    (
                        self.repository_namespace,
                        str(tenant_id),
                        str(namespace),
                        MemoryState.ACTIVE.value,
                    ),
                ).fetchall()
                for row in rows:
                    current = self._record(row)
                    if current.expires_at is None or _utc(current.expires_at) > instant:
                        continue
                    result = self._connection.execute(
                        """
                        UPDATE canonical_memory
                        SET version = ?, updated_at = ?, state = ?
                        WHERE repository_namespace = ?
                          AND memory_id = ?
                          AND version = ?
                          AND state = ?
                        """,
                        (
                            current.version + 1,
                            _iso(instant),
                            MemoryState.TOMBSTONED.value,
                            self.repository_namespace,
                            current.memory_id,
                            current.version,
                            MemoryState.ACTIVE.value,
                        ),
                    )
                    if result.rowcount != 1:
                        raise MemoryConflict("memory version conflict during expiry")
                    refreshed = self._find_memory(
                        current.memory_id,
                        tenant_id=current.tenant_id,
                        namespace=current.namespace,
                    )
                    assert refreshed is not None
                    record = self._record(refreshed)
                    self._record_revision(
                        record,
                        mutation="expire",
                        predecessor_version=current.version,
                        committed_at=instant,
                    )
                    self._record_projection_event(
                        record,
                        action="delete",
                        created_at=instant,
                    )
                    expired.append(record)
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return tuple(expired)

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class MongoMemoryRepository:
    """Async Mongo-backed canonical memory authority with injected database.

    The class intentionally depends only on the database/collection protocol,
    not Motor/PyMongo imports, so the core package remains bootable without a
    Mongo driver while backend deployments can inject an AsyncIOMotorDatabase.
    """

    def __init__(
        self,
        database,
        *,
        repository_namespace: str = "memory",
        collection_prefix: str = "canonical_memory",
    ) -> None:
        namespace = str(repository_namespace).strip()
        prefix = str(collection_prefix).strip()
        if not namespace or not prefix:
            raise ValueError("repository_namespace and collection_prefix are required")
        self.repository_namespace = namespace
        self.records = database[f"{prefix}_records"]
        self.idempotency = database[f"{prefix}_idempotency"]
        self.revisions = database[f"{prefix}_revisions"]
        self.projection_outbox = database[f"{prefix}_projection_outbox"]

    async def ensure_indexes(self) -> None:
        await self.records.create_index(
            [
                ("repository_namespace", 1),
                ("memory_id", 1),
            ],
            unique=True,
            name="canonical_memory_identity",
        )
        await self.records.create_index(
            [
                ("repository_namespace", 1),
                ("tenant_id", 1),
                ("namespace", 1),
                ("subject_id", 1),
                ("state", 1),
                ("updated_at", 1),
            ],
            name="canonical_memory_subject",
        )
        await self.idempotency.create_index(
            [
                ("repository_namespace", 1),
                ("tenant_id", 1),
                ("namespace", 1),
                ("idempotency_key", 1),
            ],
            unique=True,
            name="canonical_memory_idempotency",
        )
        await self.revisions.create_index(
            [
                ("repository_namespace", 1),
                ("memory_id", 1),
                ("version", 1),
            ],
            unique=True,
            name="canonical_memory_revision_identity",
        )
        await self.revisions.create_index(
            [
                ("repository_namespace", 1),
                ("tenant_id", 1),
                ("namespace", 1),
                ("memory_id", 1),
                ("version", 1),
            ],
            name="canonical_memory_revision_scope",
        )
        await self.projection_outbox.create_index(
            [
                ("repository_namespace", 1),
                ("event_id", 1),
            ],
            unique=True,
            name="canonical_memory_projection_event_identity",
        )
        await self.projection_outbox.create_index(
            [
                ("repository_namespace", 1),
                ("published_at", 1),
                ("created_at", 1),
                ("memory_id", 1),
                ("memory_version", 1),
            ],
            name="canonical_memory_projection_pending",
        )

    @staticmethod
    def _record_from_doc(doc: dict) -> MemoryRecord:
        return MemoryRecord(
            memory_id=doc["memory_id"],
            tenant_id=doc["tenant_id"],
            namespace=doc["namespace"],
            subject_id=doc["subject_id"],
            kind=MemoryKind(doc["kind"]),
            version=int(doc["version"]),
            created_at=_parse_time(doc["created_at"], "created_at"),
            updated_at=_parse_time(doc["updated_at"], "updated_at"),
            idempotency_key=doc["idempotency_key"],
            payload_digest=doc["payload_digest"],
            content=doc.get("content"),
            content_ref=doc.get("content_ref"),
            provenance_refs=tuple(doc.get("provenance_refs") or ()),
            source_operation_id=doc.get("source_operation_id"),
            expires_at=_parse_time(doc.get("expires_at"), "expires_at"),
            state=MemoryState(doc["state"]),
            data_class=doc["data_class"],
            schema_version=int(doc.get("schema_version", 1)),
        )

    def _record_doc(self, record: MemoryRecord) -> dict:
        return {
            "repository_namespace": self.repository_namespace,
            "memory_id": record.memory_id,
            "tenant_id": record.tenant_id,
            "namespace": record.namespace,
            "subject_id": record.subject_id,
            "kind": record.kind.value,
            "version": record.version,
            "created_at": _iso(record.created_at),
            "updated_at": _iso(record.updated_at),
            "idempotency_key": record.idempotency_key,
            "payload_digest": record.payload_digest,
            "content": record.content,
            "content_ref": record.content_ref,
            "provenance_refs": list(record.provenance_refs),
            "source_operation_id": record.source_operation_id,
            "expires_at": _iso(record.expires_at),
            "state": record.state.value,
            "data_class": record.data_class,
            "schema_version": record.schema_version,
        }

    def _scope(self, *, tenant_id: str, namespace: str) -> dict:
        return {
            "repository_namespace": self.repository_namespace,
            "tenant_id": str(tenant_id),
            "namespace": str(namespace),
        }

    def _idempotency_filter(self, proposal: MemoryWriteProposal) -> dict:
        return {
            **self._scope(
                tenant_id=proposal.tenant_id,
                namespace=proposal.namespace,
            ),
            "idempotency_key": proposal.idempotency_key,
        }

    async def _ensure_revision_and_projection(
        self,
        record: MemoryRecord,
        *,
        mutation: str,
        predecessor_version: int | None,
        projection_action: str,
        committed_at: datetime,
    ) -> None:
        revision = MemoryRevision(
            memory_id=record.memory_id,
            tenant_id=record.tenant_id,
            namespace=record.namespace,
            version=record.version,
            predecessor_version=predecessor_version,
            mutation=mutation,
            committed_at=_utc(committed_at),
            record=record,
        )
        revision_doc = {
            "repository_namespace": self.repository_namespace,
            "memory_id": revision.memory_id,
            "tenant_id": revision.tenant_id,
            "namespace": revision.namespace,
            "version": revision.version,
            "predecessor_version": revision.predecessor_version,
            "mutation": revision.mutation,
            "committed_at": _iso(revision.committed_at),
            "record": revision.record.as_dict(),
        }
        await self.revisions.update_one(
            {
                "repository_namespace": self.repository_namespace,
                "memory_id": revision.memory_id,
                "version": revision.version,
            },
            {"$setOnInsert": revision_doc},
            upsert=True,
        )

        event = MemoryProjectionEvent(
            event_id=_projection_event_id(record, projection_action),
            tenant_id=record.tenant_id,
            namespace=record.namespace,
            memory_id=record.memory_id,
            memory_version=record.version,
            action=projection_action,
            created_at=_utc(committed_at),
            record=record,
        )
        event_doc = {
            "repository_namespace": self.repository_namespace,
            "event_id": event.event_id,
            "tenant_id": event.tenant_id,
            "namespace": event.namespace,
            "memory_id": event.memory_id,
            "memory_version": event.memory_version,
            "action": event.action,
            "created_at": _iso(event.created_at),
            "published_at": None,
            "record": event.record.as_dict(),
        }
        await self.projection_outbox.update_one(
            {
                "repository_namespace": self.repository_namespace,
                "event_id": event.event_id,
            },
            {"$setOnInsert": event_doc},
            upsert=True,
        )

    @staticmethod
    def _revision_from_doc(doc: dict[str, Any]) -> MemoryRevision:
        snapshot = doc.get("record")
        if not isinstance(snapshot, dict):
            raise MemoryRepositoryError("memory revision record is corrupt")
        record = _record_from_json(
            json.dumps(snapshot, separators=(",", ":"), allow_nan=False)
        )
        return MemoryRevision(
            memory_id=doc["memory_id"],
            tenant_id=doc["tenant_id"],
            namespace=doc["namespace"],
            version=int(doc["version"]),
            predecessor_version=(
                None
                if doc.get("predecessor_version") is None
                else int(doc["predecessor_version"])
            ),
            mutation=doc["mutation"],
            committed_at=_parse_time(doc["committed_at"], "committed_at"),
            record=record,
        )

    @staticmethod
    def _projection_from_doc(doc: dict[str, Any]) -> MemoryProjectionEvent:
        snapshot = doc.get("record")
        if not isinstance(snapshot, dict):
            raise MemoryRepositoryError("projection event record is corrupt")
        record = _record_from_json(
            json.dumps(snapshot, separators=(",", ":"), allow_nan=False)
        )
        return MemoryProjectionEvent(
            event_id=doc["event_id"],
            tenant_id=doc["tenant_id"],
            namespace=doc["namespace"],
            memory_id=doc["memory_id"],
            memory_version=int(doc["memory_version"]),
            action=doc["action"],
            created_at=_parse_time(doc["created_at"], "created_at"),
            record=record,
            published_at=_parse_time(doc.get("published_at"), "published_at"),
        )

    async def _recover_reservation(
        self,
        proposal: MemoryWriteProposal,
        reservation: dict,
    ) -> MemoryRecord | None:
        if reservation.get("status") == "committed":
            snapshot = reservation.get("result")
            if not isinstance(snapshot, dict):
                raise MemoryRepositoryError("committed idempotency receipt is corrupt")
            return _record_from_json(
                json.dumps(snapshot, separators=(",", ":"), allow_nan=False)
            )

        memory_id = str(reservation.get("memory_id") or "").strip()
        if not memory_id:
            return None
        doc = await self.records.find_one(
            {
                **self._scope(
                    tenant_id=proposal.tenant_id,
                    namespace=proposal.namespace,
                ),
                "memory_id": memory_id,
            }
        )
        if doc is None:
            return None
        record = self._record_from_doc(doc)
        if (
            record.idempotency_key != proposal.idempotency_key
            or record.payload_digest != proposal.payload_digest
            or record.source_operation_id != proposal.source_operation_id
        ):
            return None
        await self._ensure_revision_and_projection(
            record,
            mutation="create" if record.version == 1 else "update",
            predecessor_version=None if record.version == 1 else record.version - 1,
            projection_action="upsert",
            committed_at=record.updated_at,
        )
        await self.idempotency.update_one(
            {
                **self._idempotency_filter(proposal),
                "request_digest": _proposal_digest(proposal),
            },
            {
                "$set": {
                    "status": "committed",
                    "result": record.as_dict(),
                    "committed_at": _iso(record.updated_at),
                }
            },
        )
        return record

    async def _reserve(
        self,
        proposal: MemoryWriteProposal,
        *,
        memory_id: str,
        instant: datetime,
    ) -> tuple[str, dict]:
        owner_token = str(uuid4())
        reservation = await self.idempotency.find_one_and_update(
            self._idempotency_filter(proposal),
            {
                "$setOnInsert": {
                    **self._idempotency_filter(proposal),
                    "request_digest": _proposal_digest(proposal),
                    "status": "pending",
                    "owner_token": owner_token,
                    "memory_id": memory_id,
                    "created_at": _iso(instant),
                }
            },
            upsert=True,
            return_document=True,
        )
        if reservation is None:
            reservation = await self.idempotency.find_one(
                self._idempotency_filter(proposal)
            )
        if reservation is None:
            raise MemoryRepositoryError("idempotency reservation was not persisted")
        if reservation.get("request_digest") != _proposal_digest(proposal):
            raise MemoryConflict(
                "idempotency_key replayed with different memory write intent"
            )
        if reservation.get("status") == "committed":
            return "replay", reservation
        if reservation.get("owner_token") == owner_token:
            return owner_token, reservation
        recovered = await self._recover_reservation(proposal, reservation)
        if recovered is not None:
            return "replay", {
                **reservation,
                "status": "committed",
                "result": recovered.as_dict(),
            }
        raise MemoryConflict("memory write with this idempotency_key is in progress")

    async def _release_failed_reservation(
        self,
        proposal: MemoryWriteProposal,
        owner_token: str,
    ) -> None:
        if owner_token in {"replay", ""}:
            return
        await self.idempotency.delete_one(
            {
                **self._idempotency_filter(proposal),
                "owner_token": owner_token,
                "status": "pending",
            }
        )

    async def _commit_reservation(
        self,
        proposal: MemoryWriteProposal,
        owner_token: str,
        record: MemoryRecord,
    ) -> None:
        result = await self.idempotency.update_one(
            {
                **self._idempotency_filter(proposal),
                "owner_token": owner_token,
                "status": "pending",
            },
            {
                "$set": {
                    "status": "committed",
                    "result": record.as_dict(),
                    "committed_at": _iso(record.updated_at),
                }
            },
        )
        if int(getattr(result, "matched_count", 1)) != 1:
            raise MemoryRepositoryError("idempotency receipt finalization failed")

    async def commit(
        self,
        proposal: MemoryWriteProposal,
        *,
        now: datetime | None = None,
    ) -> MemoryRecord:
        if not isinstance(proposal, MemoryWriteProposal):
            raise TypeError("proposal must be MemoryWriteProposal")
        instant = _utc(now)
        memory_id = proposal.target_memory_id or str(uuid4())
        owner_token, reservation = await self._reserve(
            proposal,
            memory_id=memory_id,
            instant=instant,
        )
        if owner_token == "replay":
            snapshot = reservation.get("result")
            if not isinstance(snapshot, dict):
                raise MemoryRepositoryError("committed idempotency receipt is corrupt")
            return _record_from_json(
                json.dumps(snapshot, separators=(",", ":"), allow_nan=False)
            )

        try:
            if proposal.target_memory_id is None:
                mutation = "create"
                predecessor_version = None
                record = MemoryRecord(
                    memory_id=memory_id,
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
                await self.records.insert_one(self._record_doc(record))
            else:
                current_doc = await self.records.find_one(
                    {
                        **self._scope(
                            tenant_id=proposal.tenant_id,
                            namespace=proposal.namespace,
                        ),
                        "memory_id": proposal.target_memory_id,
                    }
                )
                if current_doc is None:
                    raise MemoryNotFound("target memory not found in authority scope")
                current = self._record_from_doc(current_doc)
                if current.state is not MemoryState.ACTIVE:
                    raise MemoryConflict("tombstoned memory is not writable")
                if proposal.expected_version is None:
                    raise MemoryConflict("update requires expected_version")
                if current.version != proposal.expected_version:
                    raise MemoryConflict("memory version conflict")
                if current.subject_id != proposal.subject_id:
                    raise MemoryConflict("memory subject cannot change")
                mutation = "update"
                predecessor_version = current.version
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
                updated = await self.records.find_one_and_update(
                    {
                        **self._scope(
                            tenant_id=proposal.tenant_id,
                            namespace=proposal.namespace,
                        ),
                        "memory_id": current.memory_id,
                        "version": proposal.expected_version,
                        "state": MemoryState.ACTIVE.value,
                    },
                    {"$set": self._record_doc(record)},
                    return_document=True,
                )
                if updated is None:
                    raise MemoryConflict("memory version conflict")
                record = self._record_from_doc(updated)
            await self._ensure_revision_and_projection(
                record,
                mutation=mutation,
                predecessor_version=predecessor_version,
                projection_action="upsert",
                committed_at=instant,
            )
            await self._commit_reservation(proposal, owner_token, record)
            return record
        except (MemoryNotFound, MemoryConflict):
            await self._release_failed_reservation(proposal, owner_token)
            raise

    async def get(
        self,
        memory_id: str,
        *,
        tenant_id: str,
        namespace: str,
        include_tombstoned: bool = False,
    ) -> MemoryRecord:
        doc = await self.records.find_one(
            {
                **self._scope(tenant_id=tenant_id, namespace=namespace),
                "memory_id": str(memory_id),
            }
        )
        if doc is None:
            raise MemoryNotFound("memory not found in authority scope")
        record = self._record_from_doc(doc)
        if record.state is MemoryState.TOMBSTONED and not include_tombstoned:
            raise MemoryNotFound("memory not found in authority scope")
        return record

    async def list_subject(
        self,
        *,
        tenant_id: str,
        namespace: str,
        subject_id: str,
        include_tombstoned: bool = False,
    ) -> tuple[MemoryRecord, ...]:
        query = {
            **self._scope(tenant_id=tenant_id, namespace=namespace),
            "subject_id": str(subject_id),
        }
        if not include_tombstoned:
            query["state"] = MemoryState.ACTIVE.value
        cursor = self.records.find(query).sort(
            [("updated_at", 1), ("memory_id", 1)]
        )
        if hasattr(cursor, "to_list"):
            docs = await cursor.to_list(length=None)
        else:
            docs = [doc async for doc in cursor]
        return tuple(self._record_from_doc(doc) for doc in docs)

    async def history(
        self,
        memory_id: str,
        *,
        tenant_id: str,
        namespace: str,
    ) -> tuple[MemoryRevision, ...]:
        cursor = self.revisions.find(
            {
                "repository_namespace": self.repository_namespace,
                "memory_id": str(memory_id),
                "tenant_id": str(tenant_id),
                "namespace": str(namespace),
            }
        ).sort([("version", 1)])
        if hasattr(cursor, "to_list"):
            docs = await cursor.to_list(length=None)
        else:
            docs = [doc async for doc in cursor]
        return tuple(self._revision_from_doc(doc) for doc in docs)

    async def pending_projection_events(
        self,
        *,
        limit: int = 100,
    ) -> tuple[MemoryProjectionEvent, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("projection event limit must be an integer")
        if limit < 1:
            raise ValueError("projection event limit must be positive")
        cursor = self.projection_outbox.find(
            {
                "repository_namespace": self.repository_namespace,
                "published_at": None,
            }
        ).sort(
            [
                ("created_at", 1),
                ("memory_id", 1),
                ("memory_version", 1),
                ("event_id", 1),
            ]
        )
        if hasattr(cursor, "to_list"):
            docs = await cursor.to_list(length=limit)
        else:
            docs = []
            async for doc in cursor:
                docs.append(doc)
                if len(docs) >= limit:
                    break
        return tuple(self._projection_from_doc(doc) for doc in docs[:limit])

    async def mark_projection_published(
        self,
        event_id: str,
        *,
        now: datetime | None = None,
    ) -> MemoryProjectionEvent:
        event_key = str(event_id).strip()
        if not event_key:
            raise ValueError("projection event id must not be empty")
        instant = _utc(now)
        await self.projection_outbox.update_one(
            {
                "repository_namespace": self.repository_namespace,
                "event_id": event_key,
                "published_at": None,
            },
            {"$set": {"published_at": _iso(instant)}},
        )
        doc = await self.projection_outbox.find_one(
            {
                "repository_namespace": self.repository_namespace,
                "event_id": event_key,
            }
        )
        if doc is None:
            raise MemoryNotFound("projection event not found")
        return self._projection_from_doc(doc)

    async def tombstone(
        self,
        memory_id: str,
        *,
        tenant_id: str,
        namespace: str,
        expected_version: int,
        now: datetime | None = None,
    ) -> MemoryRecord:
        instant = _utc(now)
        current = await self.get(
            memory_id,
            tenant_id=tenant_id,
            namespace=namespace,
            include_tombstoned=True,
        )
        if current.state is MemoryState.TOMBSTONED:
            if expected_version not in {current.version, current.version - 1}:
                raise MemoryConflict("memory version conflict")
            await self._ensure_revision_and_projection(
                current,
                mutation="tombstone",
                predecessor_version=current.version - 1,
                projection_action="delete",
                committed_at=current.updated_at,
            )
            return current
        if current.version != expected_version:
            raise MemoryConflict("memory version conflict")
        updated = await self.records.find_one_and_update(
            {
                **self._scope(tenant_id=tenant_id, namespace=namespace),
                "memory_id": current.memory_id,
                "version": expected_version,
                "state": MemoryState.ACTIVE.value,
            },
            {
                "$set": {
                    "version": current.version + 1,
                    "updated_at": _iso(instant),
                    "state": MemoryState.TOMBSTONED.value,
                }
            },
            return_document=True,
        )
        if updated is None:
            raise MemoryConflict("memory version conflict")
        record = self._record_from_doc(updated)
        await self._ensure_revision_and_projection(
            record,
            mutation="tombstone",
            predecessor_version=current.version,
            projection_action="delete",
            committed_at=instant,
        )
        return record

    async def expire_due(
        self,
        *,
        tenant_id: str,
        namespace: str,
        now: datetime | None = None,
    ) -> tuple[MemoryRecord, ...]:
        """Tombstone elapsed records using the same optimistic version fence."""

        instant = _utc(now)
        cursor = self.records.find(
            {
                **self._scope(tenant_id=tenant_id, namespace=namespace),
                "state": MemoryState.ACTIVE.value,
            }
        ).sort([("expires_at", 1), ("memory_id", 1)])
        if hasattr(cursor, "to_list"):
            docs = await cursor.to_list(length=None)
        else:
            docs = [doc async for doc in cursor]

        expired: list[MemoryRecord] = []
        for doc in docs:
            current = self._record_from_doc(doc)
            if current.expires_at is None or _utc(current.expires_at) > instant:
                continue
            expired.append(
                await self.tombstone(
                    current.memory_id,
                    tenant_id=current.tenant_id,
                    namespace=current.namespace,
                    expected_version=current.version,
                    now=instant,
                )
            )
        return tuple(expired)


__all__ = [
    "MemoryConflict",
    "MemoryProjectionEvent",
    "MemoryRevision",
    "MemoryNotFound",
    "MemoryRepositoryError",
    "MongoMemoryRepository",
    "SQLiteMemoryRepository",
]

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
                    expired.append(self._record(refreshed))
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
        if current.version != expected_version:
            raise MemoryConflict("memory version conflict")
        if current.state is MemoryState.TOMBSTONED:
            return current
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
        return self._record_from_doc(updated)

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
    "MemoryNotFound",
    "MemoryRepositoryError",
    "MongoMemoryRepository",
    "SQLiteMemoryRepository",
]

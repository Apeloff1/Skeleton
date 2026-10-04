"""Durable privacy-deletion tombstones for hostile gap G016.

Deletion is not complete when one store removes a row.  Derived stores, caches,
queues, replicas, and restored snapshots can otherwise re-introduce the deleted
object.  This module makes the deletion fence durable and generation-aware.

Core laws
---------
* tombstones are tenant/resource scoped and survive process restart;
* the deletion boundary is monotonic: ``deleted_through_generation`` never
  regresses;
* the required propagation replica set can grow but cannot shrink silently;
* reads/replays at or below the deletion boundary fail closed;
* replica acknowledgements bind the exact current tombstone digest;
* advancing a tombstone invalidates every previous acknowledgement;
* compaction may issue a certificate only after every required replica has
  acknowledged the current tombstone; it never deletes the tombstone itself.

The ledger stores no deleted payload.  It stores only deletion authority,
lineage/fencing metadata, and propagation evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any, Iterable


_SCHEMA = "skeleton.deletion_tombstone.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_I64 = (1 << 63) - 1


class DeletionTombstoneError(RuntimeError):
    """Base failure for deletion/tombstone authority."""


class DeletionConflict(DeletionTombstoneError):
    """A mutation conflicts with the current deletion authority."""


class DeletionFenced(DeletionTombstoneError):
    """A read/replay/write is fenced by a deletion tombstone."""


class DeletionCorruption(DeletionTombstoneError):
    """Persisted deletion state is malformed or internally inconsistent."""


def _text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise DeletionTombstoneError(f"{field} must be canonical non-empty text")
    if len(value) > maximum:
        raise DeletionTombstoneError(f"{field} exceeds maximum length")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise DeletionTombstoneError(f"{field} contains control characters")
    return value


def _generation(value: object, field: str, *, minimum: int = 0) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > _MAX_I64
    ):
        raise DeletionTombstoneError(
            f"{field} must be an integer in [{minimum}, {_MAX_I64}]"
        )
    return value


def _now_ns(value: int | None) -> int:
    return _generation(time.time_ns() if value is None else value, "now_ns", minimum=1)


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise DeletionTombstoneError(f"{field} must be canonical lowercase SHA-256")
    return value


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DeletionTombstoneError("value is not canonical-JSON encodable") from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _replicas(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise DeletionTombstoneError("required_replicas must be an iterable of replica ids")
    normalized = tuple(sorted({_text(v, "replica_id") for v in values}))
    if not normalized:
        raise DeletionTombstoneError("required_replicas must be non-empty")
    return normalized


@dataclass(frozen=True, slots=True)
class DeletionTombstone:
    namespace: str
    tenant_id: str
    resource_kind: str
    resource_id: str
    deleted_through_generation: int
    tombstone_generation: int
    required_replicas: tuple[str, ...]
    reason_digest: str
    created_at_ns: int
    updated_at_ns: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "namespace", _text(self.namespace, "namespace"))
        object.__setattr__(self, "tenant_id", _text(self.tenant_id, "tenant_id"))
        object.__setattr__(
            self, "resource_kind", _text(self.resource_kind, "resource_kind")
        )
        object.__setattr__(self, "resource_id", _text(self.resource_id, "resource_id"))
        object.__setattr__(
            self,
            "deleted_through_generation",
            _generation(
                self.deleted_through_generation,
                "deleted_through_generation",
                minimum=0,
            ),
        )
        object.__setattr__(
            self,
            "tombstone_generation",
            _generation(self.tombstone_generation, "tombstone_generation", minimum=1),
        )
        canonical_replicas = _replicas(self.required_replicas)
        if canonical_replicas != self.required_replicas:
            raise DeletionTombstoneError(
                "required_replicas must be sorted and duplicate-free"
            )
        object.__setattr__(self, "reason_digest", _digest(self.reason_digest, "reason_digest"))
        created = _generation(self.created_at_ns, "created_at_ns", minimum=1)
        updated = _generation(self.updated_at_ns, "updated_at_ns", minimum=1)
        if updated < created:
            raise DeletionTombstoneError("updated_at_ns cannot predate created_at_ns")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": _SCHEMA,
            "namespace": self.namespace,
            "tenant_id": self.tenant_id,
            "resource_kind": self.resource_kind,
            "resource_id": self.resource_id,
            "deleted_through_generation": self.deleted_through_generation,
            "tombstone_generation": self.tombstone_generation,
            "required_replicas": list(self.required_replicas),
            "reason_digest": self.reason_digest,
        }

    @property
    def digest(self) -> str:
        return _sha256_json(self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "created_at_ns": self.created_at_ns,
            "updated_at_ns": self.updated_at_ns,
            "tombstone_digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class ReplicaDeletionAck:
    namespace: str
    tenant_id: str
    resource_kind: str
    resource_id: str
    replica_id: str
    tombstone_generation: int
    tombstone_digest: str
    deleted_through_generation: int
    acknowledged_at_ns: int

    @property
    def digest(self) -> str:
        return _sha256_json(
            {
                "schema": _SCHEMA,
                "namespace": self.namespace,
                "tenant_id": self.tenant_id,
                "resource_kind": self.resource_kind,
                "resource_id": self.resource_id,
                "replica_id": self.replica_id,
                "tombstone_generation": self.tombstone_generation,
                "tombstone_digest": self.tombstone_digest,
                "deleted_through_generation": self.deleted_through_generation,
            }
        )


@dataclass(frozen=True, slots=True)
class DeletionPropagationState:
    tombstone: DeletionTombstone
    acknowledged_replicas: tuple[str, ...]
    pending_replicas: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.pending_replicas


@dataclass(frozen=True, slots=True)
class TombstoneCompactionCertificate:
    tombstone_digest: str
    tombstone_generation: int
    acknowledged_replicas: tuple[str, ...]
    issued_at_ns: int

    @property
    def digest(self) -> str:
        return _sha256_json(
            {
                "schema": _SCHEMA,
                "tombstone_digest": self.tombstone_digest,
                "tombstone_generation": self.tombstone_generation,
                "acknowledged_replicas": list(self.acknowledged_replicas),
                "issued_at_ns": self.issued_at_ns,
            }
        )


class SQLiteDeletionTombstoneLedger:
    """Durable, generation-fenced tombstone propagation authority."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "deletion_tombstones",
    ) -> None:
        self.namespace = _text(namespace, "namespace")
        self._connection = sqlite3.connect(
            str(path),
            check_same_thread=False,
            timeout=5.0,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = FULL;
                PRAGMA busy_timeout = 5000;

                CREATE TABLE IF NOT EXISTS deletion_tombstone (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    resource_kind TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    deleted_through_generation INTEGER NOT NULL,
                    tombstone_generation INTEGER NOT NULL,
                    required_replicas_json TEXT NOT NULL,
                    reason_digest TEXT NOT NULL,
                    created_at_ns INTEGER NOT NULL,
                    updated_at_ns INTEGER NOT NULL,
                    tombstone_digest TEXT NOT NULL,
                    PRIMARY KEY(namespace, tenant_id, resource_kind, resource_id)
                );

                CREATE TABLE IF NOT EXISTS deletion_replica_ack (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    resource_kind TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    replica_id TEXT NOT NULL,
                    tombstone_generation INTEGER NOT NULL,
                    tombstone_digest TEXT NOT NULL,
                    deleted_through_generation INTEGER NOT NULL,
                    acknowledged_at_ns INTEGER NOT NULL,
                    PRIMARY KEY(
                        namespace, tenant_id, resource_kind, resource_id, replica_id
                    )
                );
                """
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "SQLiteDeletionTombstoneLedger":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def reason_digest(reason: str) -> str:
        return hashlib.sha256(_text(reason, "reason", maximum=2048).encode("utf-8")).hexdigest()

    def request_deletion(
        self,
        *,
        tenant_id: str,
        resource_kind: str,
        resource_id: str,
        deleted_through_generation: int,
        required_replicas: Iterable[str],
        reason_digest: str,
        now_ns: int | None = None,
    ) -> DeletionTombstone:
        tenant = _text(tenant_id, "tenant_id")
        kind = _text(resource_kind, "resource_kind")
        resource = _text(resource_id, "resource_id")
        deleted_through = _generation(
            deleted_through_generation,
            "deleted_through_generation",
            minimum=0,
        )
        required = _replicas(required_replicas)
        reason = _digest(reason_digest, "reason_digest")
        now = _now_ns(now_ns)

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    SELECT * FROM deletion_tombstone
                    WHERE namespace=? AND tenant_id=? AND resource_kind=? AND resource_id=?
                    """,
                    (self.namespace, tenant, kind, resource),
                ).fetchone()
                if row is None:
                    tombstone = DeletionTombstone(
                        namespace=self.namespace,
                        tenant_id=tenant,
                        resource_kind=kind,
                        resource_id=resource,
                        deleted_through_generation=deleted_through,
                        tombstone_generation=1,
                        required_replicas=required,
                        reason_digest=reason,
                        created_at_ns=now,
                        updated_at_ns=now,
                    )
                    self._connection.execute(
                        """
                        INSERT INTO deletion_tombstone VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tombstone.namespace,
                            tombstone.tenant_id,
                            tombstone.resource_kind,
                            tombstone.resource_id,
                            tombstone.deleted_through_generation,
                            tombstone.tombstone_generation,
                            _canonical_json(list(tombstone.required_replicas)),
                            tombstone.reason_digest,
                            tombstone.created_at_ns,
                            tombstone.updated_at_ns,
                            tombstone.digest,
                        ),
                    )
                    self._connection.execute("COMMIT")
                    return tombstone

                current = self._decode_tombstone(row)
                if deleted_through < current.deleted_through_generation:
                    raise DeletionConflict("deletion boundary cannot regress")
                if not set(current.required_replicas).issubset(required):
                    raise DeletionConflict("required replica set cannot shrink")

                same = (
                    deleted_through == current.deleted_through_generation
                    and required == current.required_replicas
                    and reason == current.reason_digest
                )
                if same:
                    self._connection.execute("COMMIT")
                    return current

                if deleted_through == current.deleted_through_generation and required == current.required_replicas:
                    raise DeletionConflict("reason digest cannot change without deletion advancement")

                next_tombstone = DeletionTombstone(
                    namespace=self.namespace,
                    tenant_id=tenant,
                    resource_kind=kind,
                    resource_id=resource,
                    deleted_through_generation=deleted_through,
                    tombstone_generation=current.tombstone_generation + 1,
                    required_replicas=required,
                    reason_digest=reason,
                    created_at_ns=current.created_at_ns,
                    updated_at_ns=now,
                )
                self._connection.execute(
                    """
                    UPDATE deletion_tombstone
                    SET deleted_through_generation=?, tombstone_generation=?,
                        required_replicas_json=?, reason_digest=?, updated_at_ns=?,
                        tombstone_digest=?
                    WHERE namespace=? AND tenant_id=? AND resource_kind=? AND resource_id=?
                    """,
                    (
                        next_tombstone.deleted_through_generation,
                        next_tombstone.tombstone_generation,
                        _canonical_json(list(next_tombstone.required_replicas)),
                        next_tombstone.reason_digest,
                        next_tombstone.updated_at_ns,
                        next_tombstone.digest,
                        self.namespace,
                        tenant,
                        kind,
                        resource,
                    ),
                )
                self._connection.execute(
                    """
                    DELETE FROM deletion_replica_ack
                    WHERE namespace=? AND tenant_id=? AND resource_kind=? AND resource_id=?
                    """,
                    (self.namespace, tenant, kind, resource),
                )
                self._connection.execute("COMMIT")
                return next_tombstone
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def get(
        self,
        *,
        tenant_id: str,
        resource_kind: str,
        resource_id: str,
    ) -> DeletionTombstone | None:
        tenant = _text(tenant_id, "tenant_id")
        kind = _text(resource_kind, "resource_kind")
        resource = _text(resource_id, "resource_id")
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM deletion_tombstone
                WHERE namespace=? AND tenant_id=? AND resource_kind=? AND resource_id=?
                """,
                (self.namespace, tenant, kind, resource),
            ).fetchone()
        return None if row is None else self._decode_tombstone(row)

    def assert_generation_allowed(
        self,
        *,
        tenant_id: str,
        resource_kind: str,
        resource_id: str,
        generation: int,
    ) -> None:
        candidate = _generation(generation, "generation", minimum=0)
        tombstone = self.get(
            tenant_id=tenant_id,
            resource_kind=resource_kind,
            resource_id=resource_id,
        )
        if tombstone is not None and candidate <= tombstone.deleted_through_generation:
            raise DeletionFenced(
                "resource generation is at or below durable deletion boundary"
            )

    def acknowledge_replica(
        self,
        *,
        tenant_id: str,
        resource_kind: str,
        resource_id: str,
        replica_id: str,
        tombstone_digest: str,
        deleted_through_generation: int,
        now_ns: int | None = None,
    ) -> ReplicaDeletionAck:
        tenant = _text(tenant_id, "tenant_id")
        kind = _text(resource_kind, "resource_kind")
        resource = _text(resource_id, "resource_id")
        replica = _text(replica_id, "replica_id")
        supplied_digest = _digest(tombstone_digest, "tombstone_digest")
        observed = _generation(
            deleted_through_generation,
            "deleted_through_generation",
            minimum=0,
        )
        now = _now_ns(now_ns)
        tombstone = self.get(
            tenant_id=tenant,
            resource_kind=kind,
            resource_id=resource,
        )
        if tombstone is None:
            raise DeletionConflict("cannot acknowledge a missing tombstone")
        if replica not in tombstone.required_replicas:
            raise DeletionConflict("replica is not in current required propagation set")
        if supplied_digest != tombstone.digest:
            raise DeletionConflict("replica acknowledgement binds stale tombstone digest")
        if observed != tombstone.deleted_through_generation:
            raise DeletionConflict("replica acknowledgement has stale deletion generation")

        ack = ReplicaDeletionAck(
            namespace=self.namespace,
            tenant_id=tenant,
            resource_kind=kind,
            resource_id=resource,
            replica_id=replica,
            tombstone_generation=tombstone.tombstone_generation,
            tombstone_digest=tombstone.digest,
            deleted_through_generation=tombstone.deleted_through_generation,
            acknowledged_at_ns=now,
        )
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO deletion_replica_ack (
                    namespace, tenant_id, resource_kind, resource_id, replica_id,
                    tombstone_generation, tombstone_digest,
                    deleted_through_generation, acknowledged_at_ns
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(namespace, tenant_id, resource_kind, resource_id, replica_id)
                DO UPDATE SET
                    tombstone_generation=excluded.tombstone_generation,
                    tombstone_digest=excluded.tombstone_digest,
                    deleted_through_generation=excluded.deleted_through_generation,
                    acknowledged_at_ns=excluded.acknowledged_at_ns
                """,
                (
                    ack.namespace,
                    ack.tenant_id,
                    ack.resource_kind,
                    ack.resource_id,
                    ack.replica_id,
                    ack.tombstone_generation,
                    ack.tombstone_digest,
                    ack.deleted_through_generation,
                    ack.acknowledged_at_ns,
                ),
            )
        return ack

    def propagation_state(
        self,
        *,
        tenant_id: str,
        resource_kind: str,
        resource_id: str,
    ) -> DeletionPropagationState:
        tombstone = self.get(
            tenant_id=tenant_id,
            resource_kind=resource_kind,
            resource_id=resource_id,
        )
        if tombstone is None:
            raise DeletionConflict("deletion tombstone does not exist")
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM deletion_replica_ack
                WHERE namespace=? AND tenant_id=? AND resource_kind=? AND resource_id=?
                ORDER BY replica_id
                """,
                (
                    self.namespace,
                    tombstone.tenant_id,
                    tombstone.resource_kind,
                    tombstone.resource_id,
                ),
            ).fetchall()
        acknowledged: list[str] = []
        for row in rows:
            replica = _text(row["replica_id"], "replica_id")
            if replica not in tombstone.required_replicas:
                raise DeletionCorruption("acknowledgement exists for non-required replica")
            if row["tombstone_generation"] != tombstone.tombstone_generation:
                raise DeletionCorruption("stale tombstone generation persisted in acknowledgement")
            if row["tombstone_digest"] != tombstone.digest:
                raise DeletionCorruption("stale tombstone digest persisted in acknowledgement")
            if row["deleted_through_generation"] != tombstone.deleted_through_generation:
                raise DeletionCorruption("stale deletion boundary persisted in acknowledgement")
            acknowledged.append(replica)
        ack_tuple = tuple(acknowledged)
        pending = tuple(r for r in tombstone.required_replicas if r not in set(ack_tuple))
        return DeletionPropagationState(
            tombstone=tombstone,
            acknowledged_replicas=ack_tuple,
            pending_replicas=pending,
        )

    def compaction_certificate(
        self,
        *,
        tenant_id: str,
        resource_kind: str,
        resource_id: str,
        now_ns: int | None = None,
    ) -> TombstoneCompactionCertificate:
        state = self.propagation_state(
            tenant_id=tenant_id,
            resource_kind=resource_kind,
            resource_id=resource_id,
        )
        if not state.complete:
            raise DeletionConflict("tombstone propagation is incomplete")
        return TombstoneCompactionCertificate(
            tombstone_digest=state.tombstone.digest,
            tombstone_generation=state.tombstone.tombstone_generation,
            acknowledged_replicas=state.acknowledged_replicas,
            issued_at_ns=_now_ns(now_ns),
        )

    def _decode_tombstone(self, row: sqlite3.Row) -> DeletionTombstone:
        try:
            raw_replicas = json.loads(row["required_replicas_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise DeletionCorruption("required replica payload is invalid JSON") from exc
        if not isinstance(raw_replicas, list) or not all(
            isinstance(v, str) for v in raw_replicas
        ):
            raise DeletionCorruption("required replica payload has invalid shape")
        try:
            tombstone = DeletionTombstone(
                namespace=row["namespace"],
                tenant_id=row["tenant_id"],
                resource_kind=row["resource_kind"],
                resource_id=row["resource_id"],
                deleted_through_generation=row["deleted_through_generation"],
                tombstone_generation=row["tombstone_generation"],
                required_replicas=tuple(raw_replicas),
                reason_digest=row["reason_digest"],
                created_at_ns=row["created_at_ns"],
                updated_at_ns=row["updated_at_ns"],
            )
        except DeletionTombstoneError as exc:
            raise DeletionCorruption(str(exc)) from exc
        stored_digest = row["tombstone_digest"]
        if not isinstance(stored_digest, str) or stored_digest != tombstone.digest:
            raise DeletionCorruption("persisted tombstone digest mismatch")
        return tombstone

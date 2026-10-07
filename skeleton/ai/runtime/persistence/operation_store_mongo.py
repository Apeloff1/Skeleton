"""Mongo-backed shared-network operation authority.

The canonical SQLite repository remains the portable reference. This module
provides a synchronous Mongo authority suitable for multi-host backend workers.
Operation state and its unpublished outbox are embedded in the same document so
every accepted state transition and corresponding publication intent are one
atomic Mongo document mutation; no cross-collection transaction is required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from skeleton.contracts.operation import (
    OperationContractError,
    OperationEnvelope,
    OperationState,
)
from skeleton.persistence.operation_store import (
    OperationOutboxEvent,
    OperationStoreConflict,
    OperationStoreCorruptionError,
    OperationStoreError,
    StoredOperation,
    _event_id,
)


def _utc(value: datetime | None = None, *, field: str = "time") -> datetime:
    instant = datetime.now(timezone.utc) if value is None else value
    if not isinstance(instant, datetime):
        raise OperationStoreError(f"{field} must be a datetime")
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise OperationStoreError(f"{field} must be timezone-aware")
    return instant.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat()


def _parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise OperationStoreCorruptionError(f"{field} must be persisted as text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise OperationStoreCorruptionError(
            f"{field} is not valid ISO-8601"
        ) from exc
    return _utc(parsed, field=field)


def _normalize_namespace(value: str) -> str:
    namespace = str(value).strip()
    if not namespace:
        raise ValueError("namespace must not be empty")
    return namespace


class MongoOperationStore:
    """Synchronous shared-network operation state and atomic embedded outbox."""

    def __init__(
        self,
        database: Any,
        *,
        namespace: str = "operation_state",
        collection: str = "canonical_operations",
    ) -> None:
        self.namespace = _normalize_namespace(namespace)
        collection_name = str(collection).strip()
        if not collection_name:
            raise ValueError("collection must not be empty")
        self.collection = database[collection_name]

    def ensure_indexes(self) -> None:
        self.collection.create_index(
            [("namespace", 1), ("operation_id", 1)],
            unique=True,
            name="canonical_operation_identity",
        )
        self.collection.create_index(
            [("namespace", 1), ("identity_digest", 1)],
            unique=True,
            name="canonical_operation_idempotency",
        )
        self.collection.create_index(
            [
                ("namespace", 1),
                ("outbox.published_at", 1),
                ("outbox.created_at", 1),
            ],
            name="canonical_operation_pending_outbox",
        )

    @staticmethod
    def _stored_from_doc(doc: Mapping[str, Any]) -> StoredOperation:
        try:
            envelope = OperationEnvelope(
                operation_id=doc["operation_id"],
                tenant_id=doc["tenant_id"],
                actor_id=doc["actor_id"],
                capability=doc["capability"],
                created_at=_parse_time(doc["created_at"], "created_at"),
                deadline=_parse_time(doc["deadline"], "deadline"),
                idempotency_key=doc["idempotency_key"],
                trace_id=doc["trace_id"],
                state=OperationState(doc["state"]),
            )
            version = int(doc["version"])
            if version < 1:
                raise ValueError("version must be positive")
            updated_at = _parse_time(doc["updated_at"], "updated_at")
        except (
            KeyError,
            TypeError,
            ValueError,
            OperationContractError,
        ) as exc:
            if isinstance(exc, OperationStoreCorruptionError):
                raise
            raise OperationStoreCorruptionError(
                "persisted Mongo operation violates canonical contract"
            ) from exc
        if doc.get("identity_digest") != envelope.identity_digest:
            raise OperationStoreCorruptionError(
                "persisted operation identity digest mismatch"
            )
        return StoredOperation(
            envelope=envelope,
            version=version,
            updated_at=updated_at,
        )

    @staticmethod
    def _outbox_from_doc(raw: Mapping[str, Any]) -> OperationOutboxEvent:
        try:
            version = int(raw["operation_version"])
            if version < 1:
                raise ValueError("operation_version must be positive")
            payload = raw["payload"]
            if not isinstance(payload, Mapping):
                raise TypeError("payload must be a mapping")
            published_raw = raw.get("published_at")
            return OperationOutboxEvent(
                outbox_id=str(raw["outbox_id"]),
                operation_id=str(raw["operation_id"]),
                operation_version=version,
                event_type=str(raw["event_type"]),
                payload=dict(payload),
                created_at=_parse_time(raw["created_at"], "created_at"),
                published_at=(
                    None
                    if published_raw is None
                    else _parse_time(published_raw, "published_at")
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, OperationStoreCorruptionError):
                raise
            raise OperationStoreCorruptionError(
                "persisted Mongo operation outbox entry is invalid"
            ) from exc

    def _filter(
        self,
        *,
        operation_id: str | None = None,
        identity_digest: str | None = None,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {"namespace": self.namespace}
        if operation_id is not None:
            operation = str(operation_id).strip()
            if not operation:
                raise OperationStoreError("operation_id is required")
            query["operation_id"] = operation
            return query
        if identity_digest is not None:
            digest = str(identity_digest).strip()
            if not digest:
                raise OperationStoreError("identity_digest is required")
            query["identity_digest"] = digest
            return query
        raise ValueError("operation_id or identity_digest is required")

    def _outbox_entry(
        self,
        envelope: OperationEnvelope,
        *,
        version: int,
        created_at: datetime,
    ) -> dict[str, Any]:
        state = OperationState(envelope.state).value
        return {
            "outbox_id": _event_id(
                self.namespace,
                envelope.operation_id,
                version,
            ),
            "operation_id": envelope.operation_id,
            "operation_version": version,
            "event_type": "operation." + state,
            "payload": {
                "state": state,
                "version": version,
                "trace_id": envelope.trace_id,
            },
            "created_at": _iso(created_at),
            "published_at": None,
        }

    def create(
        self,
        envelope: OperationEnvelope,
        *,
        now: datetime | None = None,
    ) -> StoredOperation:
        if not isinstance(envelope, OperationEnvelope):
            raise TypeError("envelope must be an OperationEnvelope")
        if OperationState(envelope.state) is not OperationState.CREATED:
            raise OperationStoreConflict(
                "new operation must start in created state"
            )
        instant = _utc(now, field="now")
        doc = {
            "namespace": self.namespace,
            "operation_id": envelope.operation_id,
            "identity_digest": envelope.identity_digest,
            "tenant_id": envelope.tenant_id,
            "actor_id": envelope.actor_id,
            "capability": envelope.capability,
            "created_at": _iso(envelope.created_at),
            "deadline": _iso(envelope.deadline),
            "idempotency_key": envelope.idempotency_key,
            "trace_id": envelope.trace_id,
            "state": OperationState(envelope.state).value,
            "version": 1,
            "updated_at": _iso(instant),
            "outbox": [
                self._outbox_entry(
                    envelope,
                    version=1,
                    created_at=instant,
                )
            ],
        }
        try:
            self.collection.insert_one(doc)
        except Exception:
            existing = self.collection.find_one(
                self._filter(operation_id=envelope.operation_id)
            )
            if existing is None:
                existing = self.collection.find_one(
                    self._filter(
                        identity_digest=envelope.identity_digest
                    )
                )
            if existing is None:
                raise
            stored = self._stored_from_doc(existing)
            if (
                stored.envelope.identity_digest != envelope.identity_digest
                and stored.envelope.operation_id == envelope.operation_id
            ):
                raise OperationStoreConflict(
                    "operation_id already exists with different content"
                )
            return stored
        return StoredOperation(
            envelope=envelope,
            version=1,
            updated_at=instant,
        )

    def get(self, operation_id: str) -> StoredOperation:
        doc = self.collection.find_one(
            self._filter(operation_id=operation_id)
        )
        if doc is None:
            raise OperationStoreError("unknown operation")
        return self._stored_from_doc(doc)

    def get_by_identity_digest(self, identity_digest: str) -> StoredOperation:
        doc = self.collection.find_one(
            self._filter(identity_digest=identity_digest)
        )
        if doc is None:
            raise OperationStoreError("unknown operation identity")
        return self._stored_from_doc(doc)

    def transition(
        self,
        operation_id: str,
        target: OperationState | str,
        *,
        expected_version: int | None = None,
        now: datetime | None = None,
    ) -> StoredOperation:
        if expected_version is not None and (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
        ):
            raise ValueError(
                "expected_version must be a positive integer"
            )
        instant = _utc(now, field="now")
        current = self.get(operation_id)
        if (
            expected_version is not None
            and current.version != expected_version
        ):
            raise OperationStoreConflict(
                "operation version changed before transition"
            )
        next_envelope = current.envelope.transition(target)
        next_version = current.version + 1
        result = self.collection.update_one(
            {
                **self._filter(operation_id=operation_id),
                "version": current.version,
            },
            {
                "$set": {
                    "state": OperationState(
                        next_envelope.state
                    ).value,
                    "version": next_version,
                    "updated_at": _iso(instant),
                },
                "$push": {
                    "outbox": self._outbox_entry(
                        next_envelope,
                        version=next_version,
                        created_at=instant,
                    )
                },
            },
        )
        if int(getattr(result, "modified_count", 0)) != 1:
            raise OperationStoreConflict(
                "operation version changed during transition"
            )
        return StoredOperation(
            envelope=next_envelope,
            version=next_version,
            updated_at=instant,
        )

    def pending_outbox(
        self,
        *,
        operation_id: str | None = None,
        limit: int = 1000,
    ) -> tuple[OperationOutboxEvent, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        query: dict[str, Any] = {
            "namespace": self.namespace,
            "outbox": {"$elemMatch": {"published_at": None}},
        }
        if operation_id is not None:
            operation = str(operation_id).strip()
            if not operation:
                raise OperationStoreError("operation_id is required")
            query["operation_id"] = operation

        pending: list[OperationOutboxEvent] = []
        for doc in self.collection.find(query):
            rows = doc.get("outbox")
            if not isinstance(rows, list):
                raise OperationStoreCorruptionError(
                    "operation outbox must be persisted as a list"
                )
            for raw in rows:
                if (
                    isinstance(raw, Mapping)
                    and raw.get("published_at") is None
                ):
                    pending.append(self._outbox_from_doc(raw))
        pending.sort(
            key=lambda item: (
                item.created_at,
                item.operation_id,
                item.operation_version,
            )
        )
        return tuple(pending[:limit])

    def acknowledge_outbox(
        self,
        outbox_id: str,
        *,
        published_at: datetime | None = None,
    ) -> OperationOutboxEvent:
        event_id = str(outbox_id).strip()
        if not event_id:
            raise OperationStoreError("outbox_id is required")
        doc = self.collection.find_one(
            {
                "namespace": self.namespace,
                "outbox.outbox_id": event_id,
            }
        )
        if doc is None:
            raise OperationStoreError("unknown operation outbox event")
        rows = doc.get("outbox")
        if not isinstance(rows, list):
            raise OperationStoreCorruptionError(
                "operation outbox must be persisted as a list"
            )
        raw = next(
            (
                item
                for item in rows
                if isinstance(item, Mapping)
                and item.get("outbox_id") == event_id
            ),
            None,
        )
        if raw is None:
            raise OperationStoreCorruptionError(
                "operation outbox identity disappeared"
            )
        current = self._outbox_from_doc(raw)
        if current.published_at is not None:
            return current

        instant = _utc(published_at, field="published_at")
        result = self.collection.update_one(
            {
                "namespace": self.namespace,
                "operation_id": current.operation_id,
                "outbox": {
                    "$elemMatch": {
                        "outbox_id": event_id,
                        "published_at": None,
                    }
                },
            },
            {
                "$set": {
                    "outbox.$[item].published_at": _iso(instant),
                }
            },
            array_filters=[
                {
                    "item.outbox_id": event_id,
                    "item.published_at": None,
                }
            ],
        )
        if int(getattr(result, "modified_count", 0)) != 1:
            replay = self.collection.find_one(
                {
                    "namespace": self.namespace,
                    "operation_id": current.operation_id,
                }
            )
            if replay is None:
                raise OperationStoreError("unknown operation")
            replay_rows = replay.get("outbox", [])
            replay_raw = next(
                (
                    item
                    for item in replay_rows
                    if isinstance(item, Mapping)
                    and item.get("outbox_id") == event_id
                ),
                None,
            )
            if replay_raw is None:
                raise OperationStoreCorruptionError(
                    "operation outbox identity disappeared"
                )
            return self._outbox_from_doc(replay_raw)

        return OperationOutboxEvent(
            outbox_id=current.outbox_id,
            operation_id=current.operation_id,
            operation_version=current.operation_version,
            event_type=current.event_type,
            payload=dict(current.payload),
            created_at=current.created_at,
            published_at=instant,
        )

    def close(self) -> None:
        """Repository does not own the injected Mongo client lifecycle."""


__all__ = ["MongoOperationStore"]

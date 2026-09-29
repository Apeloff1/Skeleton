"""Mongo-backed shared-network operation stream authority.

The SQLite store remains the portable reference implementation. This backend
uses Mongo transactions so sequence allocation, event insertion, terminal
finality, replay watermarks, consumer acknowledgements, and projection leases
remain coherent across hosts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import uuid4

from skeleton.frontier.runtime.operation_stream import (
    OperationEventLog,
    ReplayCursor,
    StreamBackpressureError,
    StreamContractError,
    StreamDuplicateConflictError,
    StreamEvent,
    StreamReplayGapError,
    StreamTerminalError,
)
from skeleton.frontier.runtime.operation_stream_store import (
    StreamConsumerCheckpoint,
    StreamStoreCorruptionError,
    StreamWorkerLease,
    _consumer_id,
    _worker_id,
)


def _utc(value: datetime | None = None) -> datetime:
    instant = datetime.now(timezone.utc) if value is None else value
    if not isinstance(instant, datetime):
        raise StreamContractError("timestamp must be a datetime")
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise StreamContractError("timestamp must be timezone-aware")
    return instant.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat()


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise StreamStoreCorruptionError("timestamp must be text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise StreamStoreCorruptionError("timestamp must be ISO-8601") from exc
    return _utc(parsed)


class MongoOperationEventStore:
    """Transactional shared-network implementation of operation event storage."""

    def __init__(
        self,
        database: Any,
        *,
        namespace: str = "operation_stream",
        collection_prefix: str = "operation_stream",
        capacity_per_operation: int = 100_000,
    ) -> None:
        ns = str(namespace).strip()
        prefix = str(collection_prefix).strip()
        if not ns or not prefix:
            raise ValueError("namespace and collection_prefix are required")
        if (
            isinstance(capacity_per_operation, bool)
            or not isinstance(capacity_per_operation, int)
            or capacity_per_operation < 1
        ):
            raise ValueError(
                "capacity_per_operation must be a positive integer"
            )
        self.namespace = ns
        self.capacity_per_operation = capacity_per_operation
        self.database = database
        self.heads = database[f"{prefix}_heads"]
        self.events = database[f"{prefix}_events"]
        self.consumers = database[f"{prefix}_consumers"]
        self.leases = database[f"{prefix}_leases"]

    def ensure_indexes(self) -> None:
        self.heads.create_index(
            [("namespace", 1), ("operation_id", 1)],
            unique=True,
            name="operation_stream_head_identity",
        )
        self.events.create_index(
            [
                ("namespace", 1),
                ("operation_id", 1),
                ("sequence", 1),
            ],
            unique=True,
            name="operation_stream_sequence",
        )
        self.events.create_index(
            [
                ("namespace", 1),
                ("operation_id", 1),
                ("event_id", 1),
            ],
            unique=True,
            name="operation_stream_event_identity",
        )
        self.consumers.create_index(
            [
                ("namespace", 1),
                ("operation_id", 1),
                ("consumer_id", 1),
            ],
            unique=True,
            name="operation_stream_consumer_identity",
        )
        self.consumers.create_index(
            [
                ("namespace", 1),
                ("operation_id", 1),
                ("lease_expires_at", 1),
            ],
            name="operation_stream_consumer_lease",
        )
        self.leases.create_index(
            [("namespace", 1), ("operation_id", 1)],
            unique=True,
            name="operation_stream_projection_lease",
        )

    def validate_transaction_capability(self) -> None:
        """Fail closed unless Mongo can execute an actual transaction.

        Session creation is insufficient because standalone Mongo accepts
        sessions while rejecting transactional commands. Probe a read-only
        transaction so authority selection fails at startup rather than after
        the first durable append.
        """

        try:
            with self._transaction() as session:
                with session.start_transaction():
                    self.heads.find_one(
                        {
                            "namespace": self.namespace,
                            "operation_id": "__transaction-capability-probe__",
                        },
                        {"_id": 1},
                        session=session,
                    )
        except Exception as exc:
            raise StreamContractError(
                "Mongo stream authority requires transaction-capable deployment"
            ) from exc

    def _head_filter(self, operation_id: str) -> dict[str, Any]:
        OperationEventLog(operation_id, capacity=1)
        return {
            "namespace": self.namespace,
            "operation_id": operation_id,
        }

    def _ensure_head(
        self,
        operation_id: str,
        *,
        session: Any | None = None,
    ) -> Mapping[str, Any]:
        query = self._head_filter(operation_id)
        self.heads.update_one(
            query,
            {
                "$setOnInsert": {
                    **query,
                    "latest_sequence": 0,
                    "compacted_through": 0,
                    "terminal": False,
                }
            },
            upsert=True,
            session=session,
        )
        row = self.heads.find_one(query, session=session)
        if row is None:
            raise StreamStoreCorruptionError(
                "operation stream head disappeared"
            )
        return row

    @staticmethod
    def _event_from_doc(doc: Mapping[str, Any]) -> StreamEvent:
        payload = doc.get("payload")
        if not isinstance(payload, Mapping):
            raise StreamStoreCorruptionError(
                "persisted stream payload must be an object"
            )
        try:
            return StreamEvent(
                operation_id=str(doc["operation_id"]),
                event_id=str(doc["event_id"]),
                sequence=int(doc["sequence"]),
                type=str(doc["event_type"]),
                timestamp=_parse_time(doc["timestamp"]),
                payload=dict(payload),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            StreamContractError,
        ) as exc:
            if isinstance(exc, StreamStoreCorruptionError):
                raise
            raise StreamStoreCorruptionError(
                "persisted operation event violates canonical contract"
            ) from exc

    @staticmethod
    def _consumer_from_doc(
        doc: Mapping[str, Any],
    ) -> StreamConsumerCheckpoint:
        try:
            return StreamConsumerCheckpoint(
                operation_id=str(doc["operation_id"]),
                consumer_id=_consumer_id(str(doc["consumer_id"])),
                acknowledged_through=int(doc["acknowledged_through"]),
                lease_expires_at=_parse_time(doc["lease_expires_at"]),
                updated_at=_parse_time(doc["updated_at"]),
            )
        except (KeyError, TypeError, ValueError, StreamContractError) as exc:
            raise StreamStoreCorruptionError(
                "persisted stream consumer checkpoint is invalid"
            ) from exc

    @staticmethod
    def _lease_from_doc(doc: Mapping[str, Any]) -> StreamWorkerLease:
        try:
            generation = int(doc["generation"])
            if generation < 1:
                raise ValueError("generation must be positive")
            return StreamWorkerLease(
                operation_id=str(doc["operation_id"]),
                worker_id=_worker_id(str(doc["worker_id"])),
                generation=generation,
                lease_expires_at=_parse_time(doc["lease_expires_at"]),
                updated_at=_parse_time(doc["updated_at"]),
            )
        except (KeyError, TypeError, ValueError, StreamContractError) as exc:
            raise StreamStoreCorruptionError(
                "persisted stream worker lease is invalid"
            ) from exc

    def _event_doc(self, event: StreamEvent) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "operation_id": event.operation_id,
            "event_id": event.event_id,
            "sequence": event.sequence,
            "event_type": event.type,
            "timestamp": _iso(event.timestamp),
            "payload": dict(event.payload),
        }

    def _transaction(self):
        client = getattr(self.database, "client", None)
        if client is None or not hasattr(client, "start_session"):
            raise StreamContractError(
                "Mongo stream authority requires transaction-capable client"
            )
        return client.start_session()

    def append_event(self, event: StreamEvent) -> StreamEvent:
        if not isinstance(event, StreamEvent):
            raise TypeError("event must be a StreamEvent")
        with self._transaction() as session:
            with session.start_transaction():
                duplicate = self.events.find_one(
                    {
                        "namespace": self.namespace,
                        "operation_id": event.operation_id,
                        "event_id": event.event_id,
                    },
                    session=session,
                )
                if duplicate is not None:
                    prior = self._event_from_doc(duplicate)
                    if prior.as_dict() == event.as_dict():
                        return prior
                    raise StreamDuplicateConflictError(
                        "event_id already exists with different event content"
                    )
                head = self._ensure_head(
                    event.operation_id,
                    session=session,
                )
                if bool(head.get("terminal")):
                    raise StreamTerminalError(
                        "operation stream is already terminal"
                    )
                latest = int(head.get("latest_sequence", 0))
                compacted = int(head.get("compacted_through", 0))
                if latest - compacted >= self.capacity_per_operation:
                    raise StreamBackpressureError(
                        "durable operation stream capacity reached"
                    )
                expected = latest + 1
                if event.sequence != expected:
                    raise StreamContractError(
                        "out-of-order durable sequence: "
                        f"expected {expected}, got {event.sequence}"
                    )
                self.events.insert_one(
                    self._event_doc(event),
                    session=session,
                )
                result = self.heads.update_one(
                    {
                        **self._head_filter(event.operation_id),
                        "latest_sequence": latest,
                        "terminal": False,
                    },
                    {
                        "$set": {
                            "latest_sequence": event.sequence,
                            "terminal": event.terminal,
                        }
                    },
                    session=session,
                )
                if int(getattr(result, "modified_count", 0)) != 1:
                    raise StreamDuplicateConflictError(
                        "stream head changed during append"
                    )
        return event

    def append(
        self,
        operation_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        *,
        event_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> StreamEvent:
        event_identity = event_id or str(uuid4())
        instant = _utc(timestamp)
        with self._transaction() as session:
            with session.start_transaction():
                duplicate = self.events.find_one(
                    {
                        "namespace": self.namespace,
                        "operation_id": operation_id,
                        "event_id": event_identity,
                    },
                    session=session,
                )
                if duplicate is not None:
                    prior = self._event_from_doc(duplicate)
                    if (
                        prior.type == event_type
                        and prior.timestamp == instant
                        and dict(prior.payload) == dict(payload)
                    ):
                        return prior
                    if event_id is not None and timestamp is None:
                        if (
                            prior.type == event_type
                            and dict(prior.payload) == dict(payload)
                        ):
                            return prior
                    raise StreamDuplicateConflictError(
                        "event_id already exists with different event content"
                    )
                head = self._ensure_head(operation_id, session=session)
                if bool(head.get("terminal")):
                    raise StreamTerminalError(
                        "operation stream is already terminal"
                    )
                latest = int(head.get("latest_sequence", 0))
                compacted = int(head.get("compacted_through", 0))
                if latest - compacted >= self.capacity_per_operation:
                    raise StreamBackpressureError(
                        "durable operation stream capacity reached"
                    )
                event = StreamEvent(
                    operation_id=operation_id,
                    event_id=event_identity,
                    sequence=latest + 1,
                    type=event_type,
                    timestamp=instant,
                    payload=dict(payload),
                )
                self.events.insert_one(
                    self._event_doc(event),
                    session=session,
                )
                result = self.heads.update_one(
                    {
                        **self._head_filter(operation_id),
                        "latest_sequence": latest,
                        "terminal": False,
                    },
                    {
                        "$set": {
                            "latest_sequence": event.sequence,
                            "terminal": event.terminal,
                        }
                    },
                    session=session,
                )
                if int(getattr(result, "modified_count", 0)) != 1:
                    raise StreamDuplicateConflictError(
                        "stream head changed during append"
                    )
        return event

    def replay(
        self,
        cursor: ReplayCursor,
        *,
        limit: int = 1000,
    ) -> tuple[StreamEvent, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        head = self._ensure_head(cursor.operation_id)
        compacted = int(head.get("compacted_through", 0))
        if cursor.after_sequence < compacted:
            raise StreamReplayGapError(
                "requested replay cursor predates durable retained history"
            )
        rows = self.events.find(
            {
                "namespace": self.namespace,
                "operation_id": cursor.operation_id,
                "sequence": {"$gt": cursor.after_sequence},
            }
        ).sort("sequence", 1).limit(limit)
        return tuple(self._event_from_doc(row) for row in rows)

    def register_consumer(
        self,
        operation_id: str,
        consumer_id: str,
        *,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> StreamConsumerCheckpoint:
        consumer = _consumer_id(consumer_id)
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or not 1 <= lease_seconds <= 86_400
        ):
            raise ValueError(
                "lease_seconds must be an integer between 1 and 86400"
            )
        self._ensure_head(operation_id)
        instant = _utc(now)
        expires = instant + timedelta(seconds=lease_seconds)
        query = {
            "namespace": self.namespace,
            "operation_id": operation_id,
            "consumer_id": consumer,
        }
        self.consumers.update_one(
            query,
            {
                "$setOnInsert": {
                    **query,
                    "acknowledged_through": 0,
                },
                "$set": {
                    "lease_expires_at": _iso(expires),
                    "updated_at": _iso(instant),
                },
            },
            upsert=True,
        )
        row = self.consumers.find_one(query)
        if row is None:
            raise StreamStoreCorruptionError(
                "stream consumer checkpoint disappeared"
            )
        return self._consumer_from_doc(row)

    def acknowledge_consumer(
        self,
        operation_id: str,
        consumer_id: str,
        sequence: int,
        *,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> StreamConsumerCheckpoint:
        consumer = _consumer_id(consumer_id)
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 0
        ):
            raise ValueError("sequence must be a non-negative integer")
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or not 1 <= lease_seconds <= 86_400
        ):
            raise ValueError(
                "lease_seconds must be an integer between 1 and 86400"
            )
        head = self._ensure_head(operation_id)
        latest = int(head.get("latest_sequence", 0))
        if sequence > latest:
            raise StreamContractError(
                "cannot acknowledge beyond latest durable sequence"
            )
        query = {
            "namespace": self.namespace,
            "operation_id": operation_id,
            "consumer_id": consumer,
        }
        current = self.consumers.find_one(query)
        if current is None:
            raise StreamContractError(
                "consumer must register before acknowledging"
            )
        acknowledged = max(
            int(current.get("acknowledged_through", 0)),
            sequence,
        )
        instant = _utc(now)
        expires = instant + timedelta(seconds=lease_seconds)
        self.consumers.update_one(
            query,
            {
                "$set": {
                    "acknowledged_through": acknowledged,
                    "lease_expires_at": _iso(expires),
                    "updated_at": _iso(instant),
                }
            },
        )
        row = self.consumers.find_one(query)
        if row is None:
            raise StreamStoreCorruptionError(
                "stream consumer checkpoint disappeared"
            )
        return self._consumer_from_doc(row)

    def active_consumers(
        self,
        operation_id: str,
        *,
        now: datetime | None = None,
    ) -> tuple[StreamConsumerCheckpoint, ...]:
        instant = _utc(now)
        rows = self.consumers.find(
            {
                "namespace": self.namespace,
                "operation_id": operation_id,
                "lease_expires_at": {"$gt": _iso(instant)},
            }
        ).sort([("acknowledged_through", 1), ("consumer_id", 1)])
        return tuple(self._consumer_from_doc(row) for row in rows)

    def acquire_worker_lease(
        self,
        operation_id: str,
        worker_id: str,
        *,
        lease_seconds: int = 10,
        now: datetime | None = None,
    ) -> StreamWorkerLease | None:
        worker = _worker_id(worker_id)
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or not 1 <= lease_seconds <= 300
        ):
            raise ValueError(
                "lease_seconds must be an integer between 1 and 300"
            )
        self._ensure_head(operation_id)
        instant = _utc(now)
        expires = instant + timedelta(seconds=lease_seconds)
        query = {
            "namespace": self.namespace,
            "operation_id": operation_id,
        }
        current = self.leases.find_one(query)
        generation = 1
        if current is not None:
            lease = self._lease_from_doc(current)
            if lease.lease_expires_at > instant:
                return None
            generation = lease.generation + 1
        update_filter = {
            **query,
            "$or": [
                {"lease_expires_at": {"$lte": _iso(instant)}},
                {"lease_expires_at": {"$exists": False}},
            ],
        }
        if current is None:
            update_filter = query
        try:
            result = self.leases.update_one(
                update_filter,
                {
                    "$set": {
                        **query,
                        "worker_id": worker,
                        "generation": generation,
                        "lease_expires_at": _iso(expires),
                        "updated_at": _iso(instant),
                    }
                },
                upsert=current is None,
            )
        except Exception:
            return None
        if (
            int(getattr(result, "modified_count", 0)) != 1
            and getattr(result, "upserted_id", None) is None
        ):
            return None
        return StreamWorkerLease(
            operation_id,
            worker,
            generation,
            expires,
            instant,
        )

    def renew_worker_lease(
        self,
        operation_id: str,
        worker_id: str,
        generation: int,
        *,
        lease_seconds: int = 10,
        now: datetime | None = None,
    ) -> StreamWorkerLease | None:
        worker = _worker_id(worker_id)
        if (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation < 1
        ):
            raise ValueError("generation must be a positive integer")
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or not 1 <= lease_seconds <= 300
        ):
            raise ValueError(
                "lease_seconds must be an integer between 1 and 300"
            )
        instant = _utc(now)
        expires = instant + timedelta(seconds=lease_seconds)
        result = self.leases.update_one(
            {
                "namespace": self.namespace,
                "operation_id": operation_id,
                "worker_id": worker,
                "generation": generation,
                "lease_expires_at": {"$gt": _iso(instant)},
            },
            {
                "$set": {
                    "lease_expires_at": _iso(expires),
                    "updated_at": _iso(instant),
                }
            },
        )
        if int(getattr(result, "modified_count", 0)) != 1:
            return None
        return StreamWorkerLease(
            operation_id,
            worker,
            generation,
            expires,
            instant,
        )

    def release_worker_lease(
        self,
        operation_id: str,
        worker_id: str,
        generation: int,
    ) -> bool:
        worker = _worker_id(worker_id)
        if (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation < 1
        ):
            raise ValueError("generation must be a positive integer")
        result = self.leases.delete_one(
            {
                "namespace": self.namespace,
                "operation_id": operation_id,
                "worker_id": worker,
                "generation": generation,
            }
        )
        return int(getattr(result, "deleted_count", 0)) == 1

    def active_worker_lease(
        self,
        operation_id: str,
        *,
        now: datetime | None = None,
    ) -> StreamWorkerLease | None:
        instant = _utc(now)
        row = self.leases.find_one(
            {
                "namespace": self.namespace,
                "operation_id": operation_id,
                "lease_expires_at": {"$gt": _iso(instant)},
            }
        )
        return None if row is None else self._lease_from_doc(row)

    def safe_compaction_sequence(
        self,
        operation_id: str,
        *,
        now: datetime | None = None,
    ) -> int:
        head = self._ensure_head(operation_id)
        active = self.active_consumers(operation_id, now=now)
        if not active:
            return int(head.get("compacted_through", 0))
        return max(
            int(head.get("compacted_through", 0)),
            min(item.acknowledged_through for item in active),
        )

    def compact_acknowledged(
        self,
        operation_id: str,
        *,
        now: datetime | None = None,
    ) -> int:
        return self.compact_through(
            operation_id,
            self.safe_compaction_sequence(operation_id, now=now),
        )

    def compact_through(
        self,
        operation_id: str,
        sequence: int,
    ) -> int:
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 0
        ):
            raise ValueError("sequence must be a non-negative integer")
        with self._transaction() as session:
            with session.start_transaction():
                head = self._ensure_head(
                    operation_id,
                    session=session,
                )
                current = int(head.get("compacted_through", 0))
                latest = int(head.get("latest_sequence", 0))
                if sequence > latest:
                    raise StreamContractError(
                        "cannot compact beyond latest durable sequence"
                    )
                if sequence <= current:
                    return 0
                result = self.events.delete_many(
                    {
                        "namespace": self.namespace,
                        "operation_id": operation_id,
                        "sequence": {"$lte": sequence},
                    },
                    session=session,
                )
                update = self.heads.update_one(
                    {
                        **self._head_filter(operation_id),
                        "compacted_through": current,
                    },
                    {"$set": {"compacted_through": sequence}},
                    session=session,
                )
                if int(getattr(update, "modified_count", 0)) != 1:
                    raise StreamDuplicateConflictError(
                        "stream compaction watermark changed concurrently"
                    )
                return int(getattr(result, "deleted_count", 0))

    def head(self, operation_id: str) -> dict[str, Any]:
        head = self._ensure_head(operation_id)
        return {
            "operation_id": operation_id,
            "compacted_through": int(
                head.get("compacted_through", 0)
            ),
            "latest_sequence": int(
                head.get("latest_sequence", 0)
            ),
            "terminal": bool(head.get("terminal", False)),
        }

    def close(self) -> None:
        """Store does not own the injected Mongo client lifecycle."""


__all__ = ["MongoOperationEventStore"]

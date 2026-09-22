"""Mongo-backed canonical repository for durable memory authority."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from skeleton.contracts.memory_record import (
    MemoryRecord,
    MemoryStatus,
    MemoryWriteProposal,
    MemoryWriteReceipt,
)


class MemoryRepositoryError(RuntimeError):
    """Base durable-memory repository error."""


class MemoryNotFound(MemoryRepositoryError):
    """Requested memory does not exist in the caller's exact namespace."""


class MemoryConflict(MemoryRepositoryError):
    """Concurrent or incompatible memory mutation was detected."""


def _utc(value: datetime | None = None) -> datetime:
    instant = datetime.now(timezone.utc) if value is None else value
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise MemoryRepositoryError("timestamps must be timezone-aware")
    return instant.astimezone(timezone.utc)


class MongoMemoryRepository:
    """Canonical memory repository over an injected Mongo-compatible database."""

    DEFAULT_COLLECTION = "memory_records"

    def __init__(
        self,
        database: Any,
        *,
        collection_name: str = DEFAULT_COLLECTION,
    ) -> None:
        if database is None:
            raise ValueError("database is required")
        name = str(collection_name).strip()
        if not name:
            raise ValueError("collection_name must not be empty")
        self.database = database
        self.collection_name = name

    @property
    def collection(self):
        return self.database[self.collection_name]

    def ensure_indexes(self) -> None:
        self.collection.create_index("memory_id", unique=True)
        self.collection.create_index(
            [
                ("tenant_id", 1),
                ("user_id", 1),
                ("namespace", 1),
                ("dedupe_key", 1),
            ],
            unique=True,
        )
        self.collection.create_index(
            [
                ("tenant_id", 1),
                ("user_id", 1),
                ("namespace", 1),
                ("status", 1),
                ("updated_at", -1),
            ]
        )

    @staticmethod
    def _scope(
        *,
        tenant_id: str,
        user_id: str | None,
        namespace: str,
    ) -> dict[str, Any]:
        return {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "namespace": namespace,
        }

    @staticmethod
    def _proposal_query(proposal: MemoryWriteProposal) -> dict[str, Any]:
        return {
            "tenant_id": proposal.tenant_id,
            "user_id": proposal.user_id,
            "namespace": proposal.namespace,
            "dedupe_key": proposal.dedupe_key,
        }

    @staticmethod
    def _same_material(
        record: MemoryRecord,
        proposal: MemoryWriteProposal,
    ) -> bool:
        return (
            record.kind == proposal.kind
            and record.content_ref == proposal.content_ref
            and record.content_digest == proposal.content_digest
            and dict(record.provenance) == dict(proposal.provenance)
            and record.authority_class == proposal.authority_class
            and record.confidence_band == proposal.confidence_band
            and record.data_class == proposal.data_class
            and record.purpose == proposal.purpose
            and record.retention_class == proposal.retention_class
            and record.expires_at == proposal.expires_at
        )

    def commit(
        self,
        proposal: MemoryWriteProposal,
        *,
        now: datetime | None = None,
    ) -> tuple[MemoryRecord, MemoryWriteReceipt]:
        if not isinstance(proposal, MemoryWriteProposal):
            raise TypeError("proposal must be a MemoryWriteProposal")
        instant = _utc(now)
        query = self._proposal_query(proposal)
        existing_raw = self.collection.find_one(query)

        if existing_raw is not None:
            existing = MemoryRecord.from_dict(existing_raw)
            if existing.status is not MemoryStatus.ACTIVE:
                raise MemoryConflict("dedupe identity is not active")
            if self._same_material(existing, proposal):
                return existing, MemoryWriteReceipt(
                    proposal_id=proposal.proposal_id,
                    memory_id=existing.memory_id,
                    version=existing.version,
                    content_digest=existing.content_digest,
                    committed_at=instant,
                    deduplicated=True,
                )
            next_record = MemoryRecord(
                memory_id=existing.memory_id,
                tenant_id=proposal.tenant_id,
                user_id=proposal.user_id,
                namespace=proposal.namespace,
                kind=proposal.kind,
                content_ref=proposal.content_ref,
                content_digest=proposal.content_digest,
                data_class=proposal.data_class,
                purpose=proposal.purpose,
                provenance=proposal.provenance,
                authority_class=proposal.authority_class,
                confidence_band=proposal.confidence_band,
                retention_class=proposal.retention_class,
                created_at=existing.created_at,
                updated_at=instant,
                expires_at=proposal.expires_at,
                dedupe_key=proposal.dedupe_key,
                version=existing.version + 1,
                status=MemoryStatus.ACTIVE,
            )
            result = self.collection.replace_one(
                {
                    **query,
                    "memory_id": existing.memory_id,
                    "version": existing.version,
                },
                next_record.as_dict(),
                upsert=False,
            )
            if getattr(result, "matched_count", 1) != 1:
                raise MemoryConflict("memory version changed during commit")
            return next_record, MemoryWriteReceipt(
                proposal_id=proposal.proposal_id,
                memory_id=next_record.memory_id,
                version=next_record.version,
                content_digest=next_record.content_digest,
                committed_at=instant,
                deduplicated=False,
            )

        record = MemoryRecord(
            memory_id=str(uuid4()),
            tenant_id=proposal.tenant_id,
            user_id=proposal.user_id,
            namespace=proposal.namespace,
            kind=proposal.kind,
            content_ref=proposal.content_ref,
            content_digest=proposal.content_digest,
            data_class=proposal.data_class,
            purpose=proposal.purpose,
            provenance=proposal.provenance,
            authority_class=proposal.authority_class,
            confidence_band=proposal.confidence_band,
            retention_class=proposal.retention_class,
            created_at=instant,
            updated_at=instant,
            expires_at=proposal.expires_at,
            dedupe_key=proposal.dedupe_key,
            version=1,
            status=MemoryStatus.ACTIVE,
        )
        try:
            self.collection.insert_one(record.as_dict())
        except Exception as exc:
            raced = self.collection.find_one(query)
            if raced is None:
                raise
            winner = MemoryRecord.from_dict(raced)
            if not self._same_material(winner, proposal):
                raise MemoryConflict("concurrent memory write conflicted") from exc
            return winner, MemoryWriteReceipt(
                proposal_id=proposal.proposal_id,
                memory_id=winner.memory_id,
                version=winner.version,
                content_digest=winner.content_digest,
                committed_at=instant,
                deduplicated=True,
            )

        return record, MemoryWriteReceipt(
            proposal_id=proposal.proposal_id,
            memory_id=record.memory_id,
            version=record.version,
            content_digest=record.content_digest,
            committed_at=instant,
            deduplicated=False,
        )

    def get(
        self,
        memory_id: str,
        *,
        tenant_id: str,
        user_id: str | None,
        namespace: str,
        include_inactive: bool = False,
    ) -> MemoryRecord:
        query = {
            "memory_id": memory_id,
            **self._scope(
                tenant_id=tenant_id,
                user_id=user_id,
                namespace=namespace,
            ),
        }
        if not include_inactive:
            query["status"] = MemoryStatus.ACTIVE.value
        raw = self.collection.find_one(query)
        if raw is None:
            raise MemoryNotFound(memory_id)
        return MemoryRecord.from_dict(raw)

    def list_active(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        namespace: str,
        limit: int = 100,
    ) -> tuple[MemoryRecord, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        query = {
            **self._scope(
                tenant_id=tenant_id,
                user_id=user_id,
                namespace=namespace,
            ),
            "status": MemoryStatus.ACTIVE.value,
        }
        cursor = self.collection.find(query).sort("updated_at", -1).limit(limit)
        return tuple(MemoryRecord.from_dict(raw) for raw in cursor)

    def mark_deleted(
        self,
        memory_id: str,
        *,
        tenant_id: str,
        user_id: str | None,
        namespace: str,
        now: datetime | None = None,
    ) -> MemoryRecord:
        current = self.get(
            memory_id,
            tenant_id=tenant_id,
            user_id=user_id,
            namespace=namespace,
        )
        instant = _utc(now)
        deleted = MemoryRecord(
            **{
                **current.as_dict(),
                "updated_at": instant,
                "version": current.version + 1,
                "status": MemoryStatus.DELETED,
            }
        )
        result = self.collection.replace_one(
            {
                "memory_id": current.memory_id,
                "tenant_id": current.tenant_id,
                "user_id": current.user_id,
                "namespace": current.namespace,
                "version": current.version,
            },
            deleted.as_dict(),
            upsert=False,
        )
        if getattr(result, "matched_count", 1) != 1:
            raise MemoryConflict("memory version changed during delete")
        return deleted


__all__ = [
    "MemoryConflict",
    "MemoryNotFound",
    "MemoryRepositoryError",
    "MongoMemoryRepository",
]

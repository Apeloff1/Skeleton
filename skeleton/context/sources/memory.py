"""Canonical memory authority to ContextSegment adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.context import ContextKind, ContextSegment, ContextTrust
from skeleton.contracts.memory_record import MemoryRecord


def memory_record_segment(
    record: MemoryRecord,
    *,
    tenant_id: str,
    purpose: str,
    resolved_content: str | None = None,
    now: datetime | None = None,
    priority: int = 500,
    relevance: float = 0.7,
) -> ContextSegment:
    """Project one active canonical memory record into bounded context."""

    if not isinstance(record, MemoryRecord):
        raise TypeError("record must be MemoryRecord")
    if record.tenant_id != tenant_id:
        raise PermissionError("memory record tenant mismatch")
    if not record.active:
        raise ValueError("tombstoned memory cannot enter context")

    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    instant = instant.astimezone(timezone.utc)
    if record.expires_at is not None and record.expires_at <= instant:
        raise ValueError("expired memory cannot enter context")

    content = record.content if record.content is not None else resolved_content
    if not isinstance(content, str) or not content:
        raise ValueError("memory content is not materialized")

    provenance = [
        "memory:" + record.memory_id,
        "memory-namespace:" + record.namespace,
        "memory-subject:" + record.subject_id,
        "memory-version:" + str(record.version),
        "memory-payload:" + record.payload_digest,
    ]
    provenance.extend(record.provenance_refs)
    if record.source_operation_id:
        provenance.append("operation:" + record.source_operation_id)

    segment_id = str(
        uuid5(
            NAMESPACE_URL,
            "memory-context:"
            + record.tenant_id
            + ":"
            + record.namespace
            + ":"
            + record.memory_id
            + ":"
            + str(record.version),
        )
    )
    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=ContextKind.MEMORY,
        source_type="memory",
        source_id=record.memory_id,
        content=content,
        trust_level=ContextTrust.AUTHORIZED_USER_DATA,
        data_class=record.data_class,
        tenant_id=record.tenant_id,
        purpose=purpose,
        priority=priority,
        relevance=relevance,
        created_at=record.updated_at,
        provenance=provenance,
        retention_class="memory:" + record.namespace,
        content_ref=record.content_ref,
    )


__all__ = ["memory_record_segment"]

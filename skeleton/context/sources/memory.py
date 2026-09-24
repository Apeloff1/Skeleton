"""Canonical durable memory to ContextSegment adapter."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.context import ContextKind, ContextSegment, ContextTrust
from skeleton.contracts.memory_record import MemoryRecord, MemoryState


def memory_record_segment(
    record: MemoryRecord,
    *,
    purpose: str,
    resolved_content: str | None = None,
    priority: int = 500,
    relevance: float = 0.75,
) -> ContextSegment:
    if not isinstance(record, MemoryRecord):
        raise TypeError("record must be MemoryRecord")
    if record.state is not MemoryState.ACTIVE:
        raise ValueError("tombstoned memory cannot enter active context")
    content = record.content if record.content is not None else resolved_content
    if not isinstance(content, str) or not content:
        raise ValueError("memory content is not materialized")

    provenance = [
        f"memory:{record.memory_id}",
        f"memory-version:{record.version}",
        f"memory-digest:{record.payload_digest}",
    ]
    provenance.extend(record.provenance_refs)
    if record.source_operation_id:
        provenance.append("operation:" + record.source_operation_id)

    segment_id = str(
        uuid5(
            NAMESPACE_URL,
            f"memory-context:{record.memory_id}:{record.version}:{record.payload_digest}",
        )
    )
    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=ContextKind.MEMORY,
        source_type="memory-authority",
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
        retention_class="canonical-memory",
        content_ref=record.content_ref,
    )


__all__ = ["memory_record_segment"]

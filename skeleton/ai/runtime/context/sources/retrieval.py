"""Canonical retrieval hit to ContextSegment adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.context import (
    ContextKind,
    ContextSegment,
    ContextTrust,
)
from skeleton.frontier.retrieval_context import RetrievedMemory


def _created_at(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieval created_at must be timezone-aware")
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("retrieval created_at must be ISO-8601") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("retrieval created_at must be timezone-aware")
        return parsed.astimezone(timezone.utc)
    raise ValueError("retrieval metadata requires created_at")


def retrieval_segment(
    hit: RetrievedMemory,
    *,
    tenant_id: str,
    purpose: str,
    priority: int = 400,
) -> ContextSegment:
    if not isinstance(hit, RetrievedMemory):
        raise TypeError("hit must be RetrievedMemory")
    metadata = dict(hit.metadata)
    source_tenant = metadata.get("tenant_id")
    if source_tenant not in {tenant_id, "*"}:
        raise PermissionError("retrieval hit tenant mismatch")
    data_class = metadata.get("data_class")
    if not isinstance(data_class, str) or not data_class.strip():
        raise ValueError("retrieval metadata requires data_class")
    source_purpose = metadata.get("purpose", "*")
    if source_purpose not in {purpose, "*"}:
        raise PermissionError("retrieval hit purpose mismatch")

    provenance = ["retrieval:" + hit.item_id, "repository:" + hit.source_repository]
    if hit.source_revision:
        provenance.append("revision:" + hit.source_revision)
    if hit.source_path:
        provenance.append("path:" + hit.source_path)

    segment_id = str(
        uuid5(
            NAMESPACE_URL,
            "retrieval-context:"
            + hit.source_repository
            + ":"
            + hit.item_id,
        )
    )
    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=ContextKind.RETRIEVAL_EVIDENCE,
        source_type="retrieval",
        source_id=hit.item_id,
        content=hit.content,
        trust_level=ContextTrust.UNTRUSTED_EVIDENCE,
        data_class=data_class,
        tenant_id=str(source_tenant),
        purpose=purpose,
        priority=priority,
        relevance=hit.relevance if hit.relevance is not None else 0.5,
        created_at=_created_at(metadata.get("created_at")),
        provenance=provenance,
        retention_class=str(metadata.get("retention_class") or "retrieval-cache"),
    )


__all__ = ["retrieval_segment"]

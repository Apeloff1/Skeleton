"""Artifact authority to canonical context adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.context import ContextKind, ContextSegment, ContextTrust


def artifact_segment(
    *,
    artifact_id: str,
    content: str,
    tenant_id: str,
    purpose: str,
    created_at: datetime,
    data_class: str = "internal",
    content_ref: str | None = None,
    priority: int = 450,
    relevance: float = 0.6,
    provenance: Iterable[str] = (),
    retention_class: str = "artifact",
) -> ContextSegment:
    """Project a materialized artifact into untrusted evidence context."""

    if not isinstance(artifact_id, str) or not artifact_id.strip():
        raise ValueError("artifact_id must be non-empty")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id must be non-empty")
    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("purpose must be non-empty")
    if not isinstance(content, str) or not content:
        raise ValueError("artifact content must be materialized")
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("artifact created_at must be timezone-aware")

    normalized_id = artifact_id.strip()
    normalized_tenant = tenant_id.strip()
    normalized_purpose = purpose.strip()
    segment_id = str(
        uuid5(
            NAMESPACE_URL,
            "artifact-context:"
            + normalized_tenant
            + ":"
            + normalized_id,
        )
    )
    refs = ["artifact:" + normalized_id, *tuple(provenance)]
    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=ContextKind.ARTIFACT,
        source_type="artifact",
        source_id=normalized_id,
        content=content,
        trust_level=ContextTrust.UNTRUSTED_EVIDENCE,
        data_class=data_class,
        tenant_id=normalized_tenant,
        purpose=normalized_purpose,
        priority=priority,
        relevance=relevance,
        created_at=created_at.astimezone(timezone.utc),
        provenance=refs,
        retention_class=retention_class,
        content_ref=content_ref,
    )


__all__ = ["artifact_segment"]

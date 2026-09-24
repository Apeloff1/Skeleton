"""Artifact materialization to canonical context evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.context import ContextKind, ContextSegment, ContextTrust


_ALLOWED_ARTIFACT_TRUST = {
    ContextTrust.AUTHORIZED_USER_DATA,
    ContextTrust.UNTRUSTED_EVIDENCE,
    ContextTrust.DERIVED_UNTRUSTED,
}


def artifact_segment(
    *,
    artifact_id: str,
    tenant_id: str,
    purpose: str,
    content: str,
    data_class: str,
    created_at: datetime,
    provenance: Iterable[str],
    content_ref: str | None = None,
    trust_level: ContextTrust = ContextTrust.DERIVED_UNTRUSTED,
    priority: int = 350,
    relevance: float = 0.5,
    retention_class: str = "artifact",
) -> ContextSegment:
    artifact_id = str(artifact_id).strip()
    if not artifact_id:
        raise ValueError("artifact_id is required")
    if not isinstance(content, str) or not content:
        raise ValueError("artifact content is required")
    try:
        trust = ContextTrust(trust_level)
    except ValueError as exc:
        raise ValueError("artifact trust level is invalid") from exc
    if trust not in _ALLOWED_ARTIFACT_TRUST:
        raise PermissionError("artifact content cannot become trusted control")
    if (
        not isinstance(created_at, datetime)
        or created_at.tzinfo is None
        or created_at.utcoffset() is None
    ):
        raise ValueError("artifact created_at must be timezone-aware")
    created_at = created_at.astimezone(timezone.utc)

    segment_id = str(
        uuid5(
            NAMESPACE_URL,
            "artifact-context:" + tenant_id + ":" + artifact_id,
        )
    )
    refs = ["artifact:" + artifact_id, *tuple(provenance)]
    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=ContextKind.ARTIFACT,
        source_type="artifact-authority",
        source_id=artifact_id,
        content=content,
        trust_level=trust,
        data_class=data_class,
        tenant_id=tenant_id,
        purpose=purpose,
        priority=priority,
        relevance=relevance,
        created_at=created_at,
        provenance=refs,
        retention_class=retention_class,
        content_ref=content_ref,
    )


__all__ = ["artifact_segment"]

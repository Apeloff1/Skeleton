"""Direct authenticated user input to canonical context."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.context import ContextKind, ContextSegment, ContextTrust


def user_input_segment(
    *,
    source_id: str,
    tenant_id: str,
    purpose: str,
    content: str,
    created_at: datetime,
    data_class: str = "confidential",
    priority: int = 800,
) -> ContextSegment:
    source_id = str(source_id).strip()
    if not source_id:
        raise ValueError("source_id is required")
    if not isinstance(content, str) or not content:
        raise ValueError("user input content is required")
    if (
        not isinstance(created_at, datetime)
        or created_at.tzinfo is None
        or created_at.utcoffset() is None
    ):
        raise ValueError("created_at must be timezone-aware")
    created_at = created_at.astimezone(timezone.utc)
    segment_id = str(
        uuid5(
            NAMESPACE_URL,
            "user-input-context:" + tenant_id + ":" + purpose + ":" + source_id,
        )
    )
    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=ContextKind.USER_MESSAGE,
        source_type="authenticated-user-input",
        source_id=source_id,
        content=content,
        trust_level=ContextTrust.AUTHORIZED_USER_DATA,
        data_class=data_class,
        tenant_id=tenant_id,
        purpose=purpose,
        priority=priority,
        relevance=1.0,
        created_at=created_at,
        provenance=("user-input:" + source_id,),
        retention_class="request",
    )


__all__ = ["user_input_segment"]

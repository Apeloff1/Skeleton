"""Canonical declarative skill manifests to trusted context instructions."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.context import ContextKind, ContextSegment, ContextTrust
from skeleton.skills.manifest import SkillManifest


def skill_manifest_segment(
    manifest: SkillManifest,
    *,
    purpose: str,
    created_at: datetime,
    tenant_id: str = "*",
    priority: int | None = None,
) -> ContextSegment:
    if not isinstance(manifest, SkillManifest):
        raise TypeError("manifest must be SkillManifest")
    manifest.validate()
    content = manifest.instruction_text()
    if not content:
        raise ValueError("skill has no instruction content")
    if (
        not isinstance(created_at, datetime)
        or created_at.tzinfo is None
        or created_at.utcoffset() is None
    ):
        raise ValueError("created_at must be timezone-aware")
    created_at = created_at.astimezone(timezone.utc)
    source_id = f"{manifest.name}@{manifest.version}"
    segment_id = str(uuid5(NAMESPACE_URL, "skill-context:" + source_id))
    selected_priority = manifest.priority if priority is None else priority
    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=ContextKind.SKILL_INSTRUCTION,
        source_type="skill-registry",
        source_id=source_id,
        content=content,
        trust_level=ContextTrust.TRUSTED_CONTROL,
        data_class="internal",
        tenant_id=tenant_id,
        purpose=purpose,
        priority=selected_priority,
        relevance=1.0,
        created_at=created_at,
        provenance=(
            "skill:" + source_id,
            "skill-provenance:" + manifest.provenance,
        ),
        retention_class="skill-registry",
    )


__all__ = ["skill_manifest_segment"]

"""Versioned skill files to trusted skill-instruction context adapter."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.context import ContextKind, ContextSegment, ContextTrust
from skeleton.context.skills_files import SkillSpec


def skill_instruction_segment(
    skill: SkillSpec,
    *,
    tenant_id: str,
    purpose: str,
    created_at: datetime,
    mandatory: bool = False,
    priority: int = 850,
) -> ContextSegment:
    """Project one skill definition into trusted control context."""

    if not isinstance(skill, SkillSpec):
        raise TypeError("skill must be SkillSpec")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id must be non-empty")
    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("purpose must be non-empty")
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")

    content = skill.instructions or skill.description
    if not content:
        raise ValueError("skill has no materialized instructions")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    source_id = skill.skill_id + "@" + skill.source
    segment_id = str(
        uuid5(
            NAMESPACE_URL,
            "skill-context:" + source_id + ":" + digest,
        )
    )
    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=ContextKind.SKILL_INSTRUCTION,
        source_type="skill-registry",
        source_id=source_id,
        content=content,
        trust_level=ContextTrust.TRUSTED_CONTROL,
        data_class="internal",
        tenant_id=tenant_id.strip(),
        purpose=purpose.strip(),
        priority=priority,
        relevance=1.0,
        created_at=created_at.astimezone(timezone.utc),
        provenance=(
            "skill:" + skill.skill_id,
            "skill-source:" + skill.source,
            "skill-content:" + digest,
        ),
        retention_class="skill-definition",
        mandatory=mandatory,
    )


__all__ = ["skill_instruction_segment"]

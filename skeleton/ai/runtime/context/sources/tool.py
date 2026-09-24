"""Canonical tool manifest to trusted tool-schema context adapter."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.context import ContextKind, ContextSegment, ContextTrust
from skeleton.skills.tool_contract import ToolManifest


def tool_manifest_segment(
    manifest: ToolManifest,
    *,
    tenant_id: str,
    purpose: str,
    created_at: datetime,
    mandatory: bool = False,
    priority: int = 900,
) -> ContextSegment:
    """Project one canonical tool manifest into provider-neutral schema context."""

    if not isinstance(manifest, ToolManifest):
        raise TypeError("manifest must be ToolManifest")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id must be non-empty")
    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("purpose must be non-empty")
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")

    payload = {
        "tool_id": manifest.tool_id,
        "description": manifest.description,
        "input_schema": dict(manifest.input_schema),
    }
    content = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    source_id = manifest.tool_id + "@" + manifest.version
    segment_id = str(
        uuid5(
            NAMESPACE_URL,
            "tool-schema-context:" + source_id + ":" + content,
        )
    )
    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=ContextKind.TOOL_SCHEMA,
        source_type="tool-registry",
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
            "tool-manifest:" + manifest.tool_id,
            "tool-version:" + manifest.version,
            "tool-effect:" + manifest.effect.value,
        ),
        retention_class="tool-manifest",
        mandatory=mandatory,
    )


__all__ = ["tool_manifest_segment"]

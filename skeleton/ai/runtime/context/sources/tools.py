"""Canonical tool manifests and receipts to context segments."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.context import ContextKind, ContextSegment, ContextTrust
from skeleton.skills.tool_contract import ToolExecutionReceipt, ToolManifest


def _aware(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("created_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def tool_manifest_segment(
    manifest: ToolManifest,
    *,
    purpose: str,
    created_at: datetime,
    tenant_id: str = "*",
    priority: int = 850,
    mandatory: bool = False,
) -> ContextSegment:
    if not isinstance(manifest, ToolManifest):
        raise TypeError("manifest must be ToolManifest")
    payload = {
        "tool_id": manifest.tool_id,
        "version": manifest.version,
        "description": manifest.description,
        "input_schema": manifest.input_schema,
        "effect": manifest.effect.value,
        "approval_required": manifest.approval_required,
        "compensation_tool_id": manifest.compensation_tool_id,
        "timeout_seconds": manifest.timeout_seconds,
    }
    content = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    source_id = f"{manifest.tool_id}@{manifest.version}"
    segment_id = str(uuid5(NAMESPACE_URL, "tool-schema-context:" + source_id))
    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=ContextKind.TOOL_SCHEMA,
        source_type="tool-registry",
        source_id=source_id,
        content=content,
        trust_level=ContextTrust.TRUSTED_CONTROL,
        data_class="internal",
        tenant_id=tenant_id,
        purpose=purpose,
        priority=priority,
        relevance=1.0,
        created_at=_aware(created_at),
        provenance=("tool-manifest:" + source_id,),
        retention_class="tool-registry",
        mandatory=mandatory,
    )


def tool_receipt_segment(
    receipt: ToolExecutionReceipt,
    *,
    purpose: str,
    content: str,
    data_class: str = "confidential",
    priority: int = 650,
    relevance: float = 0.8,
) -> ContextSegment:
    if not isinstance(receipt, ToolExecutionReceipt):
        raise TypeError("receipt must be ToolExecutionReceipt")
    if not isinstance(content, str) or not content:
        raise ValueError("tool result content is required")
    segment_id = str(
        uuid5(
            NAMESPACE_URL,
            "tool-result-context:"
            + receipt.receipt_id
            + ":"
            + receipt.arguments_digest,
        )
    )
    provenance = (
        "tool-receipt:" + receipt.receipt_id,
        "tool:" + receipt.tool_id,
        "operation:" + receipt.operation_id,
        "request:" + receipt.request_id,
        "arguments-digest:" + receipt.arguments_digest,
    )
    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=ContextKind.TOOL_RESULT,
        source_type="tool-runtime",
        source_id=receipt.receipt_id,
        content=content,
        trust_level=ContextTrust.UNTRUSTED_EVIDENCE,
        data_class=data_class,
        tenant_id=receipt.tenant_id,
        purpose=purpose,
        priority=priority,
        relevance=relevance,
        created_at=receipt.finished_at,
        provenance=provenance,
        retention_class="tool-result",
        content_ref=receipt.result_ref,
    )


__all__ = ["tool_manifest_segment", "tool_receipt_segment"]

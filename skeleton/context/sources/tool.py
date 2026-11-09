"""Canonical tool manifest to trusted tool-schema context adapter."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.context import ContextKind, ContextSegment, ContextTrust
from skeleton.skills.tool_contract import (
    ToolExecutionReceipt,
    ToolExecutionStatus,
    ToolManifest,
)


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


def tool_result_segment(
    receipt: ToolExecutionReceipt,
    *,
    content: str,
    purpose: str,
    priority: int = 650,
    relevance: float = 0.8,
    retention_class: str = "tool-result",
) -> ContextSegment:
    """Project one successful durable tool result into untrusted context."""

    if not isinstance(receipt, ToolExecutionReceipt):
        raise TypeError("receipt must be ToolExecutionReceipt")
    if receipt.status is not ToolExecutionStatus.SUCCEEDED:
        raise ValueError("only successful tool receipts can enter context")
    if not isinstance(content, str) or not content:
        raise ValueError("tool result content must be materialized")
    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("purpose must be non-empty")
    if not isinstance(retention_class, str) or not retention_class.strip():
        raise ValueError("retention_class must be non-empty")

    content_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    segment_id = str(
        uuid5(
            NAMESPACE_URL,
            "tool-result-context:"
            + receipt.receipt_id
            + ":"
            + content_digest,
        )
    )
    provenance = [
        "tool-receipt:" + receipt.receipt_id,
        "tool:" + receipt.tool_id,
        "operation:" + receipt.operation_id,
        "tool-arguments:" + receipt.arguments_digest,
        "tool-transfer-purpose:" + receipt.transfer_purpose,
    ]
    if receipt.execution_id is not None:
        provenance.extend(
            (
                "execution:" + receipt.execution_id,
                "turn:" + str(receipt.turn_id),
                "call:" + str(receipt.call_id),
            )
        )
    if receipt.result_ref is not None:
        provenance.append("result-ref:" + receipt.result_ref)
    if receipt.governance_decision_ref is not None:
        provenance.append(
            "governance-decision:" + receipt.governance_decision_ref
        )
    if receipt.approval_ref is not None:
        provenance.append("approval:" + receipt.approval_ref)

    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=ContextKind.TOOL_RESULT,
        source_type="tool-runtime",
        source_id=receipt.receipt_id,
        content=content,
        trust_level=ContextTrust.UNTRUSTED_EVIDENCE,
        data_class=receipt.data_class,
        tenant_id=receipt.tenant_id,
        purpose=purpose.strip(),
        priority=priority,
        relevance=relevance,
        created_at=receipt.finished_at.astimezone(timezone.utc),
        provenance=tuple(provenance),
        retention_class=retention_class.strip(),
        content_ref=receipt.result_ref,
    )


__all__ = ["tool_manifest_segment", "tool_result_segment"]

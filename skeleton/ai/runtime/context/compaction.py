"""Deterministic provenance-preserving compaction for context evidence."""

from __future__ import annotations

import hashlib
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.context import (
    ContextKind,
    ContextSegment,
    ContextTrust,
    estimate_tokens,
)


COMPACTION_VERSION = "context-compaction-v1"

_ALLOWED_KINDS = frozenset(
    {
        ContextKind.USER_MESSAGE,
        ContextKind.ASSISTANT_MESSAGE,
        ContextKind.CONVERSATION_SUMMARY,
        ContextKind.RETRIEVAL_EVIDENCE,
        ContextKind.ARTIFACT,
        ContextKind.TOOL_RESULT,
    }
)


class ContextCompactionError(ValueError):
    """A context segment cannot be compacted without losing safety metadata."""


def _bounded_excerpt(content: str, max_tokens: int) -> str:
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
        raise ContextCompactionError("max_tokens must be an integer")
    if max_tokens < 1:
        raise ContextCompactionError("max_tokens must be positive")
    if not isinstance(content, str) or not content:
        raise ContextCompactionError("source content must be materialized")

    if estimate_tokens(content) <= max_tokens:
        return content

    max_bytes = max_tokens * 3
    marker = b"\n[compacted]"
    raw = content.encode("utf-8")
    if max_bytes <= len(marker):
        excerpt = raw[:max_bytes].decode("utf-8", errors="ignore")
        if not excerpt:
            excerpt = "." * max(1, min(max_bytes, 3))
    else:
        prefix = raw[: max_bytes - len(marker)].decode(
            "utf-8",
            errors="ignore",
        )
        excerpt = prefix + marker.decode("ascii")

    while len(excerpt) > 1 and estimate_tokens(excerpt) > max_tokens:
        excerpt = excerpt[:-1]
    if estimate_tokens(excerpt) > max_tokens:
        raise ContextCompactionError(
            "max_tokens is too small for a safe compacted excerpt"
        )
    return excerpt


def compact_context_segment(
    segment: ContextSegment,
    *,
    max_tokens: int,
    compaction_version: str = COMPACTION_VERSION,
) -> ContextSegment:
    """Create a bounded derived-untrusted excerpt of one evidence segment.

    Compaction never merges authority domains. The original segment identity,
    content digest, provenance, tenant, purpose, data class, and retention class
    remain represented in the derived segment.
    """

    if not isinstance(segment, ContextSegment):
        raise TypeError("segment must be ContextSegment")
    if segment.kind not in _ALLOWED_KINDS:
        raise ContextCompactionError(
            "segment kind is not eligible for evidence compaction"
        )
    if segment.trust_level is ContextTrust.TRUSTED_CONTROL or segment.mandatory:
        raise ContextCompactionError(
            "trusted or mandatory context cannot be compacted"
        )
    if segment.content is None:
        raise ContextCompactionError(
            "segment content must be materialized before compaction"
        )
    if not isinstance(compaction_version, str) or not compaction_version.strip():
        raise ContextCompactionError(
            "compaction_version must be non-empty"
        )

    normalized_version = compaction_version.strip()
    excerpt = _bounded_excerpt(segment.content, max_tokens)
    if excerpt == segment.content:
        return segment

    if segment.kind in {
        ContextKind.USER_MESSAGE,
        ContextKind.ASSISTANT_MESSAGE,
        ContextKind.CONVERSATION_SUMMARY,
    }:
        kind = ContextKind.CONVERSATION_SUMMARY
    else:
        kind = segment.kind

    source_material = (
        segment.segment_id
        + "\x1f"
        + segment.content_digest
        + "\x1f"
        + str(max_tokens)
        + "\x1f"
        + normalized_version
    )
    source_digest = hashlib.sha256(
        source_material.encode("utf-8")
    ).hexdigest()
    segment_id = str(
        uuid5(
            NAMESPACE_URL,
            "skeleton-context-compaction:" + source_digest,
        )
    )

    provenance = (
        *segment.provenance,
        "context-compaction:" + normalized_version,
        "compacted-segment:" + segment.segment_id,
        "compacted-content-sha256:" + segment.content_digest,
        "compacted-content-ref:" + segment.content_ref,
    )

    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=kind,
        source_type="context-compaction",
        source_id="compaction:" + source_digest,
        content=excerpt,
        trust_level=ContextTrust.DERIVED_UNTRUSTED,
        data_class=segment.data_class,
        tenant_id=segment.tenant_id,
        purpose=segment.purpose,
        priority=segment.priority,
        relevance=segment.relevance,
        created_at=segment.created_at,
        provenance=provenance,
        retention_class=segment.retention_class,
        derived_from=(segment.segment_id,),
    )


__all__ = [
    "COMPACTION_VERSION",
    "ContextCompactionError",
    "compact_context_segment",
]

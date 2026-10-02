from __future__ import annotations

from datetime import datetime, timezone

import pytest

from skeleton.context.compaction import (
    ContextCompactionError,
    compact_context_segment,
)
from skeleton.contracts.context import (
    ContextKind,
    ContextSegment,
    ContextTrust,
)


def segment(
    *,
    segment_id: str,
    kind: ContextKind,
    trust: ContextTrust,
    content: str,
    mandatory: bool = False,
) -> ContextSegment:
    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=kind,
        source_type="test-source",
        source_id="source-1",
        content=content,
        trust_level=trust,
        data_class="internal",
        tenant_id="tenant-a",
        purpose="planning",
        priority=10,
        relevance=0.8,
        created_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
        provenance=("source:test",),
        retention_class="session",
        mandatory=mandatory,
    )


def test_compaction_downgrades_authorized_user_data_to_derived_untrusted() -> None:
    source = segment(
        segment_id="00000000-0000-4000-8000-000000000001",
        kind=ContextKind.USER_MESSAGE,
        trust=ContextTrust.AUTHORIZED_USER_DATA,
        content="user evidence " * 200,
    )
    compacted = compact_context_segment(source, max_tokens=24)

    assert compacted is not source
    assert compacted.trust_level is ContextTrust.DERIVED_UNTRUSTED
    assert compacted.tenant_id == source.tenant_id
    assert compacted.purpose == source.purpose
    assert compacted.data_class == source.data_class
    assert compacted.retention_class == source.retention_class
    assert compacted.derived_from == (source.segment_id,)
    assert f"compacted-segment:{source.segment_id}" in compacted.provenance
    assert (
        f"compacted-content-sha256:{source.content_digest}"
        in compacted.provenance
    )


def test_compaction_never_upgrades_untrusted_retrieval_evidence() -> None:
    source = segment(
        segment_id="00000000-0000-4000-8000-000000000002",
        kind=ContextKind.RETRIEVAL_EVIDENCE,
        trust=ContextTrust.UNTRUSTED_EVIDENCE,
        content="retrieved evidence " * 200,
    )
    compacted = compact_context_segment(source, max_tokens=24)

    assert compacted.trust_level is ContextTrust.DERIVED_UNTRUSTED
    assert compacted.kind is ContextKind.RETRIEVAL_EVIDENCE


@pytest.mark.parametrize(
    "kind",
    (
        ContextKind.SYSTEM_POLICY,
        ContextKind.PRODUCT_INSTRUCTION,
        ContextKind.OPERATION_OBJECTIVE,
    ),
)
def test_trusted_control_cannot_be_compacted(kind: ContextKind) -> None:
    source = segment(
        segment_id="00000000-0000-4000-8000-000000000003",
        kind=kind,
        trust=ContextTrust.TRUSTED_CONTROL,
        content="mandatory authority rule " * 50,
    )
    with pytest.raises(ContextCompactionError, match="trusted or mandatory"):
        compact_context_segment(source, max_tokens=24)


def test_mandatory_control_cannot_be_compacted() -> None:
    source = segment(
        segment_id="00000000-0000-4000-8000-000000000004",
        kind=ContextKind.SYSTEM_POLICY,
        trust=ContextTrust.TRUSTED_CONTROL,
        content="never relax this authority boundary",
        mandatory=True,
    )
    with pytest.raises(ContextCompactionError, match="trusted or mandatory"):
        compact_context_segment(source, max_tokens=8)


def test_compaction_identity_remains_bound_to_source_segment() -> None:
    content = "same evidence " * 200
    left = segment(
        segment_id="00000000-0000-4000-8000-000000000005",
        kind=ContextKind.ARTIFACT,
        trust=ContextTrust.UNTRUSTED_EVIDENCE,
        content=content,
    )
    right = segment(
        segment_id="00000000-0000-4000-8000-000000000006",
        kind=ContextKind.ARTIFACT,
        trust=ContextTrust.UNTRUSTED_EVIDENCE,
        content=content,
    )

    compacted_left = compact_context_segment(left, max_tokens=24)
    compacted_right = compact_context_segment(right, max_tokens=24)

    assert compacted_left.content_digest == compacted_right.content_digest
    assert compacted_left.segment_id != compacted_right.segment_id
    assert compacted_left.derived_from == (left.segment_id,)
    assert compacted_right.derived_from == (right.segment_id,)

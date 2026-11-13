"""The sealed authority evidence bundle owns aggregate resource accounting."""
from __future__ import annotations

from datetime import datetime, timezone

from skeleton.ai.runtime.contracts.execution_authority import (
    AuthorityEvidenceBundle,
    AuthorityRevocationReceipt,
    ResourceUsage,
)


_NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)


def _bundle() -> AuthorityEvidenceBundle:
    return AuthorityEvidenceBundle(
        authority_digest="a" * 64,
        admission_receipt_digest="b" * 64,
        operation_id="operation-001",
        execution_id="execution-001",
        consumption_count=0,
        latest_consumption_digest=None,
        final_usage=ResourceUsage(tool_calls=1, input_tokens=9),
        descendant_usage=ResourceUsage(tool_calls=2, output_tokens=5),
        revoked=False,
        sealed_at=_NOW,
    )


def test_aggregate_usage_is_on_evidence_bundle_not_revocation_receipt() -> None:
    assert not hasattr(AuthorityRevocationReceipt, "aggregate_usage")
    bundle = _bundle()
    assert bundle.aggregate_usage.tool_calls == 3
    assert bundle.aggregate_usage.input_tokens == 9
    assert bundle.aggregate_usage.output_tokens == 5


def test_sealed_payload_and_digest_include_combined_usage() -> None:
    bundle = _bundle()
    payload = bundle.canonical_payload()
    assert payload["final_usage"]["tool_calls"] == 1
    assert payload["descendant_usage"]["tool_calls"] == 2
    assert payload["aggregate_usage"]["tool_calls"] == 3
    evidence = bundle.as_execution_evidence()
    assert evidence["digest"] == bundle.digest
    assert evidence["payload"] == payload


def test_aggregate_usage_never_mutates_separate_receipts() -> None:
    bundle = _bundle()
    for _ in range(3):
        assert bundle.aggregate_usage.tool_calls == 3
    assert bundle.final_usage.tool_calls == 1
    assert bundle.descendant_usage.tool_calls == 2

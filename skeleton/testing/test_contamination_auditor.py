from __future__ import annotations

from skeleton.ai.runtime.deferred.research_evaluation_assurance import (
    audit_contamination,
    fingerprint_text,
)


A = "a" * 64
B = "b" * 64


def test_exact_fingerprint_overlap_is_confirmed_contamination() -> None:
    result = audit_contamination(
        "audit-1",
        train_digests=(A, B),
        eval_digests=(B,),
    )
    assert result.status == "confirmed"
    assert result.exact_overlaps == (B,)
    assert len(result.audit_digest) == 64


def test_approximate_signal_is_suspected_and_no_signal_is_clean() -> None:
    suspected = audit_contamination(
        "audit-2",
        train_digests=(A,),
        eval_digests=(B,),
        approximate_overlap_count=1,
    )
    assert suspected.status == "suspected"

    clean = audit_contamination(
        "audit-3",
        train_digests=(A,),
        eval_digests=(B,),
    )
    assert clean.status == "clean"


def test_text_fingerprint_is_whitespace_normalized_and_stable() -> None:
    assert fingerprint_text("a   b\nc") == fingerprint_text("a b c")

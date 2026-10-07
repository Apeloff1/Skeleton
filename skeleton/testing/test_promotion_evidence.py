from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.promotion_evidence import (
    PROMOTION_EVIDENCE_SCHEMA_ID,
    PromotionEvidenceError,
    PromotionEvidenceReceipt,
)


HEAD = "a" * 40
CONFIG = "b" * 64
ENVIRONMENT = "c" * 64
VERIFIER = "d" * 64
TESTS = "e" * 64
NOW = datetime(2026, 9, 27, 16, 0, tzinfo=timezone.utc)


def _evidence(source: str, digest_char: str) -> EvidenceRef:
    return EvidenceRef(
        source=source,
        digest=digest_char * 64,
        category="test",
    )


def _receipt(**overrides: object) -> PromotionEvidenceReceipt:
    values: dict[str, object] = {
        "repository": "Apeloff1/Skeleton",
        "commit_sha": HEAD,
        "task_id": "P1-EVID-01",
        "accountability_id": "ACC-P1-EVID-01",
        "configuration_digest": CONFIG,
        "environment_digest": ENVIRONMENT,
        "verifier_id": "ci:p1-evidence",
        "verifier_digest": VERIFIER,
        "test_manifest_digest": TESTS,
        "run_id": "36300000000",
        "run_attempt": 1,
        "observed_at": NOW,
        "evidence": (
            _evidence("pytest:test-a", "1"),
            _evidence("pytest:test-b", "2"),
        ),
    }
    values.update(overrides)
    return PromotionEvidenceReceipt(**values)


def test_receipt_binds_exact_subject_and_evidence() -> None:
    receipt = _receipt()

    payload = receipt.to_payload()

    assert payload["schema_id"] == PROMOTION_EVIDENCE_SCHEMA_ID
    assert payload["commit_sha"] == HEAD
    assert payload["task_id"] == "P1-EVID-01"
    assert payload["accountability_id"] == "ACC-P1-EVID-01"
    assert payload["subject_digest"] == receipt.subject_digest
    assert payload["evidence_digest"] == receipt.evidence_digest
    assert len(receipt.receipt_digest) == 64
    assert receipt.matches_head(HEAD)


def test_independent_gates_join_on_subject_without_sharing_receipt_identity() -> None:
    left = _receipt(
        verifier_id="ci:quality",
        verifier_digest="3" * 64,
        run_id="quality-1",
        evidence=(_evidence("quality:result", "4"),),
    )
    right = _receipt(
        verifier_id="ci:security",
        verifier_digest="5" * 64,
        test_manifest_digest="6" * 64,
        run_id="security-1",
        run_attempt=2,
        evidence=(_evidence("security:result", "7"),),
    )

    assert left.same_subject(right)
    assert left.subject_digest == right.subject_digest
    assert left.receipt_digest != right.receipt_digest
    assert left.evidence_digest != right.evidence_digest


def test_subject_changes_when_head_config_or_environment_changes() -> None:
    baseline = _receipt()

    for field, value in (
        ("commit_sha", "f" * 40),
        ("configuration_digest", "8" * 64),
        ("environment_digest", "9" * 64),
    ):
        changed = _receipt(**{field: value})
        assert changed.subject_digest != baseline.subject_digest
        assert not baseline.same_subject(changed)


def test_verifier_and_test_manifest_change_receipt_not_subject() -> None:
    baseline = _receipt()
    changed = _receipt(
        verifier_id="ci:independent",
        verifier_digest="8" * 64,
        test_manifest_digest="9" * 64,
    )

    assert changed.subject_digest == baseline.subject_digest
    assert changed.receipt_digest != baseline.receipt_digest


def test_evidence_order_and_duplicates_are_canonicalized() -> None:
    first = _evidence("pytest:a", "1")
    second = _evidence("pytest:b", "2")

    left = _receipt(evidence=(first, second, first))
    right = _receipt(evidence=(second, first))

    assert left.evidence == right.evidence
    assert left.evidence_digest == right.evidence_digest
    assert left.receipt_digest == right.receipt_digest


def test_timestamp_is_normalized_to_utc() -> None:
    local = datetime(
        2026,
        9,
        27,
        18,
        0,
        tzinfo=timezone(timedelta(hours=2)),
    )
    receipt = _receipt(observed_at=local)

    assert receipt.observed_at == NOW
    assert receipt.to_payload()["observed_at"] == "2026-09-27T16:00:00Z"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("commit_sha", "A" * 40, "commit_sha"),
        ("configuration_digest", "b" * 63, "configuration_digest"),
        ("environment_digest", "G" * 64, "environment_digest"),
        ("verifier_digest", "short", "verifier_digest"),
        ("test_manifest_digest", "e" * 63, "test_manifest_digest"),
        ("run_attempt", 0, "run_attempt"),
        ("run_attempt", True, "run_attempt"),
    ),
)
def test_invalid_exact_identity_fields_fail_closed(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(PromotionEvidenceError, match=message):
        _receipt(**{field: value})


def test_missing_or_malformed_evidence_fails_closed() -> None:
    with pytest.raises(PromotionEvidenceError, match="requires references"):
        _receipt(evidence=())

    with pytest.raises(PromotionEvidenceError, match="evidence.digest"):
        _receipt(
            evidence=(
                EvidenceRef(
                    source="pytest:test",
                    digest="bad",
                    category="test",
                ),
            )
        )


def test_stale_head_is_detected_without_mutating_receipt() -> None:
    receipt = _receipt()

    assert not receipt.matches_head("f" * 40)
    assert not receipt.matches_head("short")
    assert receipt.commit_sha == HEAD


def test_schema_version_fails_closed() -> None:
    with pytest.raises(PromotionEvidenceError, match="unsupported"):
        _receipt(schema_version=2)

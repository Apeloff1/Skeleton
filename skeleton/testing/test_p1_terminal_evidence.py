from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.p1_terminal_evidence import (
    P1_TERMINAL_REQUIRED_TASKS,
    P1TerminalEvidenceError,
    aggregate_p1_terminal_evidence,
)
from skeleton.contracts.promotion_evidence import PromotionEvidenceReceipt


HEAD = "a" * 40
REPOSITORY = "Apeloff1/Skeleton"
VOLUMES = ("VOL-001", "VOL-002", "VOL-003")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _receipt(
    task_id: str,
    accountability_id: str,
    *,
    head: str = HEAD,
    repository: str = REPOSITORY,
) -> PromotionEvidenceReceipt:
    digit = str(
        (sum(ord(ch) for ch in task_id) % 8) + 1
    )
    return PromotionEvidenceReceipt(
        repository=repository,
        commit_sha=head,
        task_id=task_id,
        accountability_id=accountability_id,
        configuration_digest=digit * 64,
        environment_digest="9" * 64,
        verifier_id=f"pytest:{task_id.lower()}",
        verifier_digest="b" * 64,
        test_manifest_digest="c" * 64,
        run_id=f"run-{task_id.lower()}",
        run_attempt=1,
        observed_at=datetime(
            2026,
            9,
            28,
            12,
            0,
            tzinfo=timezone.utc,
        ),
        evidence=(
            EvidenceRef(
                source=f"pytest://{task_id}",
                digest="d" * 64,
                category="exact_head_verification",
            ),
        ),
    )


def _receipts() -> tuple[PromotionEvidenceReceipt, ...]:
    return tuple(
        _receipt(task_id, accountability_id)
        for task_id, accountability_id
        in P1_TERMINAL_REQUIRED_TASKS
    )


def _maturity_record(
    key: str,
    *,
    eligible: bool = True,
    current_valid: bool = True,
    blockers: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "volume_key": key,
        "lane_id": "P1-L1",
        "target_floor": "verified",
        "target_floor_eligible": eligible,
        "current_claim_valid": current_valid,
        "current_claim_blockers": list(blockers),
        "promotion_candidate": (
            None if not eligible else "verified"
        ),
    }


def _maturity_report(
    *,
    records: list[dict[str, object]] | None = None,
    source_mutation_detected: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "engine": "p1-maturity-reconciliation-v1",
        "source_digests": {
            "master_plan": "1" * 64,
            "accountability": "2" * 64,
            "p1_execution_map": "3" * 64,
            "engine_contract": "4" * 64,
            "engine_runner": "5" * 64,
        },
        "source_mutation_detected": source_mutation_detected,
        "volume_count": len(VOLUMES),
        "promotion_candidate_count": len(VOLUMES),
        "target_floor_eligible_count": len(VOLUMES),
        "current_status_counts": {"verified": len(VOLUMES)},
        "promotion_candidate_counts": {
            "verified": len(VOLUMES),
        },
        "records": (
            records
            if records is not None
            else [_maturity_record(key) for key in VOLUMES]
        ),
    }
    payload["report_digest"] = _digest(payload)
    return payload


def test_exact_head_terminal_bundle_can_be_promotion_ready() -> None:
    decision = aggregate_p1_terminal_evidence(
        receipts=_receipts(),
        maturity_report=_maturity_report(),
        expected_repository=REPOSITORY,
        expected_head=HEAD,
        expected_primary_volumes=VOLUMES,
    )

    assert decision.accepted is True
    assert decision.promotion_ready is True
    assert decision.reasons == ()
    assert decision.promotion_blockers == ()
    assert decision.primary_volume_count == len(VOLUMES)
    assert len(decision.task_evidence) == len(
        P1_TERMINAL_REQUIRED_TASKS
    )
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "p1_terminal_evidence_bundle"
    assert evidence.digest == decision.decision_digest


def test_explicit_maturity_blocker_preserves_valid_bundle_but_blocks_readiness() -> None:
    records = [
        _maturity_record("VOL-001"),
        _maturity_record(
            "VOL-002",
            eligible=False,
            current_valid=False,
            blockers=("verified: independent verification is unsigned",),
        ),
        _maturity_record("VOL-003"),
    ]
    report = _maturity_report(records=records)
    report["target_floor_eligible_count"] = 2
    report["promotion_candidate_count"] = 2
    report["report_digest"] = _digest(
        {k: v for k, v in report.items() if k != "report_digest"}
    )

    decision = aggregate_p1_terminal_evidence(
        receipts=_receipts(),
        maturity_report=report,
        expected_repository=REPOSITORY,
        expected_head=HEAD,
        expected_primary_volumes=VOLUMES,
    )

    assert decision.accepted is True
    assert decision.promotion_ready is False
    assert decision.reasons == ()
    assert decision.blocking_volume_keys == ("VOL-002",)
    assert "target-floor-not-eligible:VOL-002" in decision.promotion_blockers
    assert "current-claim-invalid:VOL-002" in decision.promotion_blockers
    assert any(
        item.startswith("maturity:VOL-002:")
        for item in decision.promotion_blockers
    )
    assert decision.accepted_evidence_ref().digest == decision.decision_digest


def test_missing_terminal_task_receipt_rejects_bundle() -> None:
    decision = aggregate_p1_terminal_evidence(
        receipts=_receipts()[1:],
        maturity_report=_maturity_report(),
        expected_repository=REPOSITORY,
        expected_head=HEAD,
        expected_primary_volumes=VOLUMES,
    )

    assert decision.accepted is False
    assert decision.promotion_ready is False
    assert (
        "missing-task-receipt:P1-EVID-06"
        in decision.reasons
    )
    with pytest.raises(
        P1TerminalEvidenceError,
        match="cannot become evidence",
    ):
        decision.accepted_evidence_ref()


def test_unknown_terminal_task_receipt_rejects_bundle() -> None:
    unknown = _receipt("P1-UNKNOWN-01", "ACC-P1-UNKNOWN-01")
    decision = aggregate_p1_terminal_evidence(
        receipts=(*_receipts(), unknown),
        maturity_report=_maturity_report(),
        expected_repository=REPOSITORY,
        expected_head=HEAD,
        expected_primary_volumes=VOLUMES,
    )

    assert decision.accepted is False
    assert "unknown-task-receipt:P1-UNKNOWN-01" in decision.reasons


def test_duplicate_task_receipt_rejects_bundle() -> None:
    receipts = _receipts()
    decision = aggregate_p1_terminal_evidence(
        receipts=(*receipts, receipts[0]),
        maturity_report=_maturity_report(),
        expected_repository=REPOSITORY,
        expected_head=HEAD,
        expected_primary_volumes=VOLUMES,
    )

    assert decision.accepted is False
    assert "duplicate-task-receipt:P1-EVID-06" in decision.reasons


def test_stale_head_and_wrong_repository_fail_closed() -> None:
    receipts = list(_receipts())
    receipts[0] = replace(receipts[0], commit_sha="b" * 40)
    receipts[1] = replace(
        receipts[1],
        repository="Other/Skeleton",
    )

    decision = aggregate_p1_terminal_evidence(
        receipts=tuple(receipts),
        maturity_report=_maturity_report(),
        expected_repository=REPOSITORY,
        expected_head=HEAD,
        expected_primary_volumes=VOLUMES,
    )

    assert decision.accepted is False
    assert "exact-head-mismatch:P1-EVID-06" in decision.reasons
    assert "repository-mismatch:P1-PROD-04" in decision.reasons


def test_accountability_substitution_fails_closed() -> None:
    receipts = list(_receipts())
    receipts[0] = replace(
        receipts[0],
        accountability_id="ACC-P1-EVID-05",
    )

    decision = aggregate_p1_terminal_evidence(
        receipts=tuple(receipts),
        maturity_report=_maturity_report(),
        expected_repository=REPOSITORY,
        expected_head=HEAD,
        expected_primary_volumes=VOLUMES,
    )

    assert decision.accepted is False
    assert "accountability-mismatch:P1-EVID-06" in decision.reasons


def test_missing_or_unknown_maturity_volume_rejects_bundle() -> None:
    report = _maturity_report(
        records=[
            _maturity_record("VOL-001"),
            _maturity_record("VOL-002"),
            _maturity_record("VOL-999"),
        ]
    )
    report["report_digest"] = _digest(
        {k: v for k, v in report.items() if k != "report_digest"}
    )

    decision = aggregate_p1_terminal_evidence(
        receipts=_receipts(),
        maturity_report=report,
        expected_repository=REPOSITORY,
        expected_head=HEAD,
        expected_primary_volumes=VOLUMES,
    )

    assert decision.accepted is False
    assert "missing-maturity-volume:VOL-003" in decision.reasons
    assert "unknown-maturity-volume:VOL-999" in decision.reasons


def test_duplicate_maturity_volume_rejects_bundle() -> None:
    report = _maturity_report(
        records=[
            _maturity_record("VOL-001"),
            _maturity_record("VOL-001"),
            _maturity_record("VOL-002"),
            _maturity_record("VOL-003"),
        ]
    )
    report["report_digest"] = _digest(
        {k: v for k, v in report.items() if k != "report_digest"}
    )

    decision = aggregate_p1_terminal_evidence(
        receipts=_receipts(),
        maturity_report=report,
        expected_repository=REPOSITORY,
        expected_head=HEAD,
        expected_primary_volumes=VOLUMES,
    )

    assert decision.accepted is False
    assert "duplicate-maturity-volume:VOL-001" in decision.reasons


def test_maturity_report_digest_tampering_is_rejected() -> None:
    report = _maturity_report()
    report["report_digest"] = "0" * 64

    with pytest.raises(
        P1TerminalEvidenceError,
        match="digest mismatch",
    ):
        aggregate_p1_terminal_evidence(
            receipts=_receipts(),
            maturity_report=report,
            expected_repository=REPOSITORY,
            expected_head=HEAD,
            expected_primary_volumes=VOLUMES,
        )


def test_source_mutation_flag_rejects_bundle() -> None:
    report = _maturity_report(source_mutation_detected=True)

    decision = aggregate_p1_terminal_evidence(
        receipts=_receipts(),
        maturity_report=report,
        expected_repository=REPOSITORY,
        expected_head=HEAD,
        expected_primary_volumes=VOLUMES,
    )

    assert decision.accepted is False
    assert "maturity-source-mutation-detected" in decision.reasons

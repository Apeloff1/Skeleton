from __future__ import annotations

from datetime import datetime, timezone

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.promotion_evidence import PromotionEvidenceReceipt
from skeleton.contracts.reproducibility import (
    ReplayDisposition,
    ReplayObservation,
    ReproducibilityError,
    bundle_from_receipt,
    evaluate_replay,
)


HEAD = "a" * 40
CONFIG = "b" * 64
ENVIRONMENT = "c" * 64
VERIFIER = "d" * 64
TESTS = "e" * 64
RUNNER = "f" * 64
BUDGET = "1" * 64
NOW = datetime(2026, 9, 27, 20, 0, tzinfo=timezone.utc)
EPOCH = 1_798_000_000


def _evidence(source: str = "tests:test", char: str = "2") -> EvidenceRef:
    return EvidenceRef(source=source, digest=char * 64, category="test")


def _receipt(**overrides: object) -> PromotionEvidenceReceipt:
    values: dict[str, object] = {
        "repository": "Apeloff1/Skeleton",
        "commit_sha": HEAD,
        "task_id": "P1-EVID-05",
        "accountability_id": "ACC-P1-EVID-05",
        "configuration_digest": CONFIG,
        "environment_digest": ENVIRONMENT,
        "verifier_id": "ci:p1-reproducibility",
        "verifier_digest": VERIFIER,
        "test_manifest_digest": TESTS,
        "run_id": "baseline-run",
        "run_attempt": 1,
        "observed_at": NOW,
        "evidence": (_evidence(),),
    }
    values.update(overrides)
    return PromotionEvidenceReceipt(**values)


def _bundle(receipt: PromotionEvidenceReceipt | None = None):
    return bundle_from_receipt(
        receipt or _receipt(),
        runner_id="pytest-manifest",
        runner_digest=RUNNER,
        budget_id="focused-ci",
        budget_digest=BUDGET,
        source_date_epoch=EPOCH,
        inputs=(
            EvidenceRef(
                source="machine/ai_p1_task_backlog.json",
                digest="3" * 64,
                category="configuration",
            ),
            EvidenceRef(
                source="tests/test_p1_reproducibility_bundle.py",
                digest="4" * 64,
                category="test_manifest",
            ),
        ),
    )


def _replay(receipt: PromotionEvidenceReceipt | None = None, **overrides: object):
    values: dict[str, object] = {
        "runner_id": "pytest-manifest",
        "runner_digest": RUNNER,
        "budget_id": "focused-ci",
        "budget_digest": BUDGET,
        "source_date_epoch": EPOCH,
        "receipt": receipt
        or _receipt(
            run_id="independent-run",
            run_attempt=2,
            observed_at=datetime(2026, 9, 27, 20, 5, tzinfo=timezone.utc),
        ),
    }
    values.update(overrides)
    return ReplayObservation(**values)


def test_independent_run_identity_can_reproduce_same_evidence() -> None:
    bundle = _bundle()
    replay = _replay()

    evaluation = evaluate_replay(bundle, replay)

    assert evaluation.disposition is ReplayDisposition.REPRODUCED
    assert evaluation.compatible is True
    assert evaluation.reproduced is True
    assert evaluation.incompatibilities == ()
    assert len(bundle.bundle_digest) == 64
    assert len(evaluation.evaluation_digest) == 64


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("runner_id", "different-runner"),
        ("runner_digest", "5" * 64),
        ("budget_id", "different-budget"),
        ("budget_digest", "6" * 64),
        ("source_date_epoch", EPOCH + 1),
    ),
)
def test_replay_infrastructure_drift_is_deterministically_incompatible(
    field: str,
    value: object,
) -> None:
    evaluation = evaluate_replay(
        _bundle(),
        _replay(**{field: value}),
    )

    assert evaluation.disposition is ReplayDisposition.INCOMPATIBLE
    assert evaluation.compatible is False
    assert evaluation.reproduced is False
    assert any(field in reason for reason in evaluation.incompatibilities)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("commit_sha", "9" * 40),
        ("configuration_digest", "5" * 64),
        ("environment_digest", "6" * 64),
        ("verifier_digest", "7" * 64),
        ("test_manifest_digest", "8" * 64),
    ),
)
def test_receipt_identity_drift_is_incompatible(
    field: str,
    value: object,
) -> None:
    changed = _receipt(
        run_id="independent-run",
        run_attempt=2,
        **{field: value},
    )
    evaluation = evaluate_replay(_bundle(), _replay(receipt=changed))

    assert evaluation.disposition is ReplayDisposition.INCOMPATIBLE
    assert any(field in reason for reason in evaluation.incompatibilities)


def test_evidence_drift_is_incompatible_even_when_subject_matches() -> None:
    changed = _receipt(
        run_id="independent-run",
        evidence=(_evidence("tests:different", "9"),),
    )

    evaluation = evaluate_replay(_bundle(), _replay(receipt=changed))

    assert evaluation.disposition is ReplayDisposition.INCOMPATIBLE
    assert evaluation.replay_subject_digest == _bundle().expected_subject_digest
    assert "evidence_digest mismatch" in "\n".join(evaluation.incompatibilities)


def test_failed_replay_is_not_misreported_as_incompatibility() -> None:
    replay = ReplayObservation(
        runner_id="pytest-manifest",
        runner_digest=RUNNER,
        budget_id="focused-ci",
        budget_digest=BUDGET,
        source_date_epoch=EPOCH,
        failure_digest="9" * 64,
    )

    evaluation = evaluate_replay(_bundle(), replay)

    assert evaluation.disposition is ReplayDisposition.FAILED
    assert evaluation.compatible is True
    assert evaluation.reproduced is False
    assert evaluation.failure_digest == "9" * 64




def test_failed_replay_with_infrastructure_drift_is_incompatible() -> None:
    replay = ReplayObservation(
        runner_id="different-runner",
        runner_digest="5" * 64,
        budget_id="different-budget",
        budget_digest="6" * 64,
        source_date_epoch=EPOCH + 1,
        failure_digest="9" * 64,
    )

    evaluation = evaluate_replay(_bundle(), replay)

    assert evaluation.disposition is ReplayDisposition.INCOMPATIBLE
    assert evaluation.compatible is False
    assert evaluation.reproduced is False
    assert evaluation.failure_digest == "9" * 64
    assert any("runner_id mismatch" in item for item in evaluation.incompatibilities)
    assert any("budget_id mismatch" in item for item in evaluation.incompatibilities)
    assert any(
        "source_date_epoch mismatch" in item
        for item in evaluation.incompatibilities
    )


def test_bundle_input_order_and_duplicates_are_canonicalized() -> None:
    receipt = _receipt()
    first = EvidenceRef(
        source="tests/a.py",
        digest="3" * 64,
        category="test",
    )
    second = EvidenceRef(
        source="tests/b.py",
        digest="4" * 64,
        category="test",
    )
    left = bundle_from_receipt(
        receipt,
        runner_id="pytest-manifest",
        runner_digest=RUNNER,
        budget_id="focused-ci",
        budget_digest=BUDGET,
        source_date_epoch=EPOCH,
        inputs=(first, second, first),
    )
    right = bundle_from_receipt(
        receipt,
        runner_id="pytest-manifest",
        runner_digest=RUNNER,
        budget_id="focused-ci",
        budget_digest=BUDGET,
        source_date_epoch=EPOCH,
        inputs=(second, first),
    )

    assert left.inputs == right.inputs
    assert left.bundle_digest == right.bundle_digest


def test_planned_input_is_rejected() -> None:
    with pytest.raises(ReproducibilityError, match="materialized"):
        bundle_from_receipt(
            _receipt(),
            runner_id="pytest-manifest",
            runner_digest=RUNNER,
            budget_id="focused-ci",
            budget_digest=BUDGET,
            source_date_epoch=EPOCH,
            inputs=(
                EvidenceRef(
                    source="planned:tests/future.py",
                    digest="3" * 64,
                    category="test",
                ),
            ),
        )


def test_missing_receipt_requires_failure_digest() -> None:
    with pytest.raises(ReproducibilityError, match="failure_digest"):
        ReplayObservation(
            runner_id="pytest-manifest",
            runner_digest=RUNNER,
            budget_id="focused-ci",
            budget_digest=BUDGET,
            source_date_epoch=EPOCH,
        )


def test_successful_receipt_cannot_carry_failure_digest() -> None:
    with pytest.raises(ReproducibilityError, match="cannot include"):
        ReplayObservation(
            runner_id="pytest-manifest",
            runner_digest=RUNNER,
            budget_id="focused-ci",
            budget_digest=BUDGET,
            source_date_epoch=EPOCH,
            receipt=_receipt(),
            failure_digest="9" * 64,
        )

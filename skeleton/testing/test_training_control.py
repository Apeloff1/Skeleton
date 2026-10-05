"""Regressions for the unsigned P3T2-TRAINING-01 ledger."""

from __future__ import annotations

import hashlib

import pytest

from skeleton.training.control import (
    GovernedTrainingLedger,
    RunAdmission,
    TrainingContractError,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _admit() -> tuple[GovernedTrainingLedger, RunAdmission]:
    ledger = GovernedTrainingLedger()
    admission = RunAdmission(
        run_id="run-143",
        tenant_id="house",
        dataset_digest=_sha("dataset"),
        base_checkpoint_digest=_sha("base"),
        trainer_actor="trainer",
        max_steps=3,
        max_tokens=30,
    )
    ledger.admit(admission)
    return ledger, admission


def test_admission_is_idempotent_and_rejects_rebind() -> None:
    ledger, admission = _admit()
    again = ledger.admit(admission)
    assert again == admission
    with pytest.raises(TrainingContractError):
        ledger.admit(
            RunAdmission(
                run_id=admission.run_id,
                tenant_id="other",
                dataset_digest=admission.dataset_digest,
                base_checkpoint_digest=admission.base_checkpoint_digest,
                trainer_actor=admission.trainer_actor,
                max_steps=admission.max_steps,
                max_tokens=admission.max_tokens,
            )
        )


def test_checkpoint_cursor_budget_and_crash_recovery() -> None:
    ledger, _admission = _admit()
    digest = ledger.stage_checkpoint(run_id="run-143", step=1, token_delta=10, payload=b"ckpt-1")
    with pytest.raises(TrainingContractError):
        ledger.resume(run_id="run-143")
    receipt = ledger.finalize_checkpoint(run_id="run-143")
    assert receipt.digest == digest
    assert receipt.cursor == 1
    resumed = ledger.resume(run_id="run-143")
    assert resumed.digest == digest
    with pytest.raises(TrainingContractError):
        ledger.stage_checkpoint(run_id="run-143", step=1, token_delta=1, payload=b"rewind")
    with pytest.raises(TrainingContractError):
        ledger.stage_checkpoint(run_id="run-143", step=2, token_delta=100, payload=b"over-budget")


def test_trainer_cannot_sign_evaluation_and_lineage_has_no_promotion() -> None:
    ledger, _admission = _admit()
    ledger.stage_checkpoint(run_id="run-143", step=1, token_delta=4, payload=b"ckpt-1")
    receipt = ledger.finalize_checkpoint(run_id="run-143")
    with pytest.raises(TrainingContractError):
        ledger.evaluate(
            run_id="run-143",
            checkpoint_digest=receipt.digest,
            evaluator_actor="trainer",
            metrics={"loss": 0.2},
            passed=True,
        )
    evaluation = ledger.evaluate(
        run_id="run-143",
        checkpoint_digest=receipt.digest,
        evaluator_actor="eval-independent",
        metrics={"loss": 0.2},
        passed=True,
    )
    lineage = ledger.lineage(run_id="run-143")
    assert lineage.evaluation_digest == evaluation.metric_digest
    assert lineage.promotion_authority is False

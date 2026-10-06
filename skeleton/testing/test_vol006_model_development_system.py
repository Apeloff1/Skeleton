from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from skeleton.modeling.evaluation import (
    EvaluationError,
    EvaluationEvidence,
    assess_eligibility,
)
from skeleton.modeling.publication import (
    ArtifactPublisher,
    CompletionMismatch,
    TrainingCompletion,
    complete_execution,
)
from skeleton.modeling.registry import (
    DatasetManifest,
    ModelArtifact,
    ModelDevelopmentRegistry,
    TrainingRun,
)
from skeleton.modeling.training import (
    ReplayError,
    StepReceipt,
    TrainingBudget,
    TrainingCheckpoint,
    TrainingExecution,
)


def _digest(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


def _dataset() -> DatasetManifest:
    return DatasetManifest(
        dataset_id="dataset-demo",
        content_digest=_digest("dataset-content"),
        rights="owned",
        integrity_digest=_digest("dataset-integrity"),
        pii_policy="none",
        dedup_digest=_digest("dataset-dedup"),
        contamination_digest=_digest("dataset-contamination"),
        sources=("source-a", "source-b"),
        metadata={"split": "train", "version": 1},
    )


def _run(dataset_digest: str) -> TrainingRun:
    return TrainingRun(
        run_id="run-demo",
        dataset_digests=(dataset_digest,),
        code_digest=_digest("training-code"),
        config_digest=_digest("training-config"),
        hardware_digest=_digest("training-hardware"),
        seed=17,
        status="completed",
    )


def _budget() -> TrainingBudget:
    return TrainingBudget(
        max_steps=8,
        max_tokens=1_000,
        max_compute_units=1_000,
        max_checkpoints=4,
    )


def _receipts(run_digest: str) -> tuple[StepReceipt, StepReceipt]:
    return (
        StepReceipt(
            run_digest=run_digest,
            ordinal=1,
            input_digest=_digest("step-1-input"),
            output_digest=_digest("step-1-output"),
            tokens=40,
            compute_units=25,
            metrics={"loss": 1.0},
        ),
        StepReceipt(
            run_digest=run_digest,
            ordinal=2,
            input_digest=_digest("step-2-input"),
            output_digest=_digest("step-2-output"),
            tokens=45,
            compute_units=30,
            metrics={"loss": 0.5},
        ),
    )


def _execute(
    run_digest: str,
) -> tuple[TrainingExecution, tuple[StepReceipt, StepReceipt], TrainingCheckpoint]:
    execution = TrainingExecution(run_digest, _budget(), seed=17)
    receipts = _receipts(run_digest)
    execution.record_step(receipts[0])
    execution.checkpoint()
    execution.record_step(receipts[1])
    checkpoint = execution.checkpoint()
    return execution, receipts, checkpoint


def test_model_development_full_lifecycle_is_deterministic_and_evidence_bound() -> None:
    registry = ModelDevelopmentRegistry()
    dataset = _dataset()
    dataset_digest = registry.add_dataset(dataset)
    run = _run(dataset_digest)
    run_digest = registry.add_run(run)

    execution, receipts, checkpoint = _execute(run_digest)
    recovery = TrainingExecution(run_digest, _budget(), seed=17)
    recovered_state = recovery.recover(checkpoint, receipts)
    assert recovered_state == checkpoint.state_digest

    completion = complete_execution(execution)
    assert completion.run_digest == run_digest
    assert completion.seed == run.seed
    assert completion.tokens == 85
    assert completion.compute_units == 55
    assert completion.receipt_digests == tuple(
        receipt.receipt_digest for receipt in receipts
    )
    assert completion.authority_scope == "research-only"

    suite_digest = _digest("evaluation-suite-v1")
    artifact = ModelArtifact(
        artifact_id="artifact-demo",
        content_digest=_digest("artifact-content"),
        training_run_digest=run_digest,
        evaluation_digest=suite_digest,
        format="safetensors",
        metadata={"parameters": 1024},
    )
    publisher = ArtifactPublisher(registry)
    artifact_digest = publisher.publish(run, completion, artifact)

    evidence = EvaluationEvidence(
        artifact_digest=artifact_digest,
        completion_digest=completion.completion_digest,
        suite_digest=suite_digest,
        metrics={"quality": 0.93, "contamination_rate": 0.0},
        passed=True,
    )
    eligibility = assess_eligibility(artifact, completion, evidence)

    assert artifact.authority_scope == "research-only"
    assert evidence.authority_scope == "evidence-only"
    assert eligibility.authority_scope == "eligibility-only"
    assert eligibility.eligible is True
    assert publisher.verify(completion, artifact_digest) is True

    lineage = registry.lineage(artifact_digest)
    assert lineage.run_digest == run_digest
    assert lineage.dataset_digests == (dataset_digest,)
    assert lineage.hardware_digest == run.hardware_digest
    assert lineage.evaluation_digest == suite_digest
    assert registry.verify(artifact_digest, lineage) is True

    # Reconstruct the complete evidence chain independently from the same
    # declared inputs and prove all content-addressed identities are stable.
    replay_registry = ModelDevelopmentRegistry()
    replay_dataset_digest = replay_registry.add_dataset(_dataset())
    replay_run = _run(replay_dataset_digest)
    replay_run_digest = replay_registry.add_run(replay_run)
    replay_execution, replay_receipts, replay_checkpoint = _execute(
        replay_run_digest
    )
    replay_completion = complete_execution(replay_execution)
    replay_artifact = replace(
        artifact,
        training_run_digest=replay_run_digest,
    )
    replay_publisher = ArtifactPublisher(replay_registry)
    replay_artifact_digest = replay_publisher.publish(
        replay_run,
        replay_completion,
        replay_artifact,
    )

    assert replay_dataset_digest == dataset_digest
    assert replay_run_digest == run_digest
    assert replay_checkpoint.checkpoint_digest == checkpoint.checkpoint_digest
    assert tuple(r.receipt_digest for r in replay_receipts) == tuple(
        r.receipt_digest for r in receipts
    )
    assert replay_completion.completion_digest == completion.completion_digest
    assert replay_artifact_digest == artifact_digest
    assert replay_registry.snapshot_digest() == registry.snapshot_digest()


def test_checkpoint_replay_rejects_receipt_chain_tampering() -> None:
    registry = ModelDevelopmentRegistry()
    dataset_digest = registry.add_dataset(_dataset())
    run_digest = registry.add_run(_run(dataset_digest))
    _execution, receipts, checkpoint = _execute(run_digest)

    tampered = replace(
        receipts[1],
        output_digest=_digest("tampered-output"),
    )
    recovery = TrainingExecution(run_digest, _budget(), seed=17)

    with pytest.raises(ReplayError, match="checkpoint receipt chain mismatch"):
        recovery.recover(checkpoint, (receipts[0], tampered))


def test_publication_and_evaluation_fail_closed_on_lineage_mismatch() -> None:
    registry = ModelDevelopmentRegistry()
    dataset_digest = registry.add_dataset(_dataset())
    run = _run(dataset_digest)
    run_digest = registry.add_run(run)
    execution, _receipts, _checkpoint = _execute(run_digest)
    completion = complete_execution(execution)
    suite_digest = _digest("evaluation-suite-v1")
    artifact = ModelArtifact(
        artifact_id="artifact-demo",
        content_digest=_digest("artifact-content"),
        training_run_digest=run_digest,
        evaluation_digest=suite_digest,
        format="safetensors",
    )
    publisher = ArtifactPublisher(registry)

    wrong_seed_completion = TrainingCompletion(
        run_digest=completion.run_digest,
        final_state_digest=completion.final_state_digest,
        receipt_digests=completion.receipt_digests,
        seed=completion.seed + 1,
        tokens=completion.tokens,
        compute_units=completion.compute_units,
    )
    with pytest.raises(CompletionMismatch, match="completion seed mismatch"):
        publisher.publish(run, wrong_seed_completion, artifact)

    artifact_digest = publisher.publish(run, completion, artifact)
    evidence = EvaluationEvidence(
        artifact_digest=artifact_digest,
        completion_digest=completion.completion_digest,
        suite_digest=_digest("wrong-suite"),
        metrics={"quality": 1.0},
        passed=True,
    )
    with pytest.raises(EvaluationError, match="evaluation suite mismatch"):
        assess_eligibility(artifact, completion, evidence)

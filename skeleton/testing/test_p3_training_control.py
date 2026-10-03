from __future__ import annotations

import pytest

from skeleton.ai.runtime.learning_foundation.data import DatasetRegistry
from skeleton.ai.runtime.learning_foundation.training import (
    LocalTrainingControlPlane,
    MetricGate,
    TrainingControlError,
)
from skeleton.learning.model_program import ReferenceNGramTrainer, TrainingSpec


def _fixture():
    registry = DatasetRegistry()
    first, _ = registry.ingest(
        ingestion_id="train-a-v1",
        dataset_id="train-a",
        samples=[b"alpha beta gamma", b"alpha beta delta"],
        source_refs=("source:a",),
        rights_refs=("rights:a",),
    )
    second, _ = registry.ingest(
        ingestion_id="train-b-v1",
        dataset_id="train-b",
        samples=[b"gamma delta epsilon"],
        source_refs=("source:b",),
        rights_refs=("rights:b",),
    )
    corpora = {
        first.identity: ("alpha beta gamma", "alpha beta delta"),
        second.identity: ("gamma delta epsilon",),
    }
    spec = TrainingSpec(
        run_id="run-1",
        model_id="local-t2-model",
        dataset_ids=(first.identity, second.identity),
        trainer_id=ReferenceNGramTrainer.trainer_id,
        code_revision="test-head",
        seed=7,
        hyperparameters={"order": 2},
    )
    return (first, second), corpora, spec


def test_local_training_plan_checkpoint_and_observability_are_deterministic() -> None:
    datasets, corpora, spec = _fixture()
    plane = LocalTrainingControlPlane()
    run = plane.run(
        spec,
        datasets=datasets,
        corpora=corpora,
        worker_ids=("worker-a", "worker-b"),
        min_workers=1,
    )
    replay = plane.run(
        spec,
        datasets=datasets,
        corpora=corpora,
        worker_ids=("worker-a", "worker-b"),
        min_workers=1,
    )

    assert replay == run
    assert [shard.worker_id for shard in run.plan.shards] == ["worker-a", "worker-b"]
    assert run.checkpoint.spec_digest == spec.digest
    assert run.checkpoint.model_digest == run.artifact.model_digest
    assert run.observation.metrics["documents"] == 3.0
    assert run.receipt.dataset_digests == tuple(
        dataset.training_content_digest for dataset in datasets
    )


def test_elastic_recovery_fails_capacity_closed_without_losing_checkpoint() -> None:
    datasets, corpora, spec = _fixture()
    plane = LocalTrainingControlPlane()
    run = plane.run(
        spec,
        datasets=datasets,
        corpora=corpora,
        worker_ids=("a", "b", "c"),
        min_workers=2,
    )
    insufficient = plane.recover(
        run.checkpoint,
        available_workers=("a",),
        required_workers=2,
    )
    assert insufficient.status == "insufficient_capacity"

    recovered = plane.recover(
        run.checkpoint,
        available_workers=("a", "c"),
        required_workers=2,
    )
    assert recovered.status == "resumable"
    assert recovered.checkpoint_digest == run.checkpoint.content_digest


def test_evaluation_gate_requires_independent_verifier() -> None:
    datasets, corpora, spec = _fixture()
    plane = LocalTrainingControlPlane()
    run = plane.run(
        spec,
        datasets=datasets,
        corpora=corpora,
        worker_ids=("worker",),
    )
    with pytest.raises(TrainingControlError, match="independently verify"):
        plane.evaluate(
            run.spec.run_id,
            gates=(MetricGate("documents", minimum=1),),
            verifier_id=ReferenceNGramTrainer.trainer_id,
        )

    decision = plane.evaluate(
        run.spec.run_id,
        gates=(
            MetricGate("documents", minimum=3),
            MetricGate("order", minimum=2, maximum=2),
        ),
        verifier_id="independent-eval-v1",
    )
    assert decision.passed is True
    post = plane.post_train(run.spec.run_id, decision)
    assert post.isolated is True
    assert post.promotion_eligible is True


def test_failed_metric_gate_blocks_post_training_promotion() -> None:
    datasets, corpora, spec = _fixture()
    plane = LocalTrainingControlPlane()
    run = plane.run(
        spec,
        datasets=datasets,
        corpora=corpora,
        worker_ids=("worker",),
    )
    decision = plane.evaluate(
        run.spec.run_id,
        gates=(MetricGate("documents", minimum=99),),
        verifier_id="independent-eval-v1",
    )
    assert decision.passed is False
    assert plane.post_train(run.spec.run_id, decision).promotion_eligible is False


def test_binary_dataset_cannot_silently_enter_text_training() -> None:
    registry = DatasetRegistry()
    record, _ = registry.ingest(
        ingestion_id="binary-v1",
        dataset_id="binary",
        samples=[b"\xff\xfe\x00"],
        source_refs=("source:binary",),
        rights_refs=("rights:binary",),
    )
    with pytest.raises(Exception, match="text-decodable"):
        record.as_training_dataset()

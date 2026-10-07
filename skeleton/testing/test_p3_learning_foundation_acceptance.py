from __future__ import annotations

import hashlib

from skeleton.ai.runtime.learning_foundation.data import DatasetRegistry
from skeleton.ai.runtime.learning_foundation.learning import (
    CurriculumStage,
    LearningProgram,
    ReinforcementEnvironment,
    VerifierCandidate,
)
from skeleton.ai.runtime.learning_foundation.multimodal import (
    LearningModality,
    MultimodalCorpus,
)
from skeleton.ai.runtime.learning_foundation.training import (
    LocalTrainingControlPlane,
    MetricGate,
)
from skeleton.learning.model_program import ReferenceNGramTrainer, TrainingSpec


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_p3_t2_provider_independent_learning_to_multimodal_acceptance() -> None:
    datasets = DatasetRegistry()
    train, ingest = datasets.ingest(
        ingestion_id="t2-train-v1",
        dataset_id="t2-train",
        samples=[
            b"local models preserve evidence identity",
            b"training recovery preserves checkpoints",
            b"multimodal retrieval preserves provenance",
        ],
        source_refs=("source:t2-fixture",),
        rights_refs=("rights:t2-fixture",),
        lineage_refs=("lineage:p3-t1",),
        expected_version=0,
    )
    assert train.quality is not None
    assert train.quality.quality_score == 1.0
    assert ingest.committed_version == 1

    corpus = {train.identity: tuple(
        payload.decode("utf-8")
        for payload in (
            b"local models preserve evidence identity",
            b"training recovery preserves checkpoints",
            b"multimodal retrieval preserves provenance",
        )
    )}
    spec = TrainingSpec(
        run_id="p3-t2-acceptance-run",
        model_id="p3-t2-local-model",
        dataset_ids=(train.identity,),
        trainer_id=ReferenceNGramTrainer.trainer_id,
        code_revision="p3-t2-acceptance",
        seed=42,
        hyperparameters={"order": 2},
    )
    training = LocalTrainingControlPlane()
    run = training.run(
        spec,
        datasets=(train,),
        corpora=corpus,
        worker_ids=("local-worker-a", "local-worker-b"),
        min_workers=1,
    )
    recovery = training.recover(
        run.checkpoint,
        available_workers=("local-worker-b",),
        required_workers=1,
    )
    assert recovery.status == "resumable"
    gate = training.evaluate(
        run.spec.run_id,
        gates=(
            MetricGate("documents", minimum=3),
            MetricGate("tokens", minimum=10),
        ),
        verifier_id="p3-t2-independent-training-verifier",
    )
    assert gate.passed is True
    post = training.post_train(run.spec.run_id, gate)
    assert post.promotion_eligible is True

    learning = LearningProgram()
    environment = ReinforcementEnvironment(
        environment_id="p3-t2-eval-env",
        observation_schema_digest=_sha("t2-observation-schema"),
        action_schema_digest=_sha("t2-action-schema"),
        reward_min=-1.0,
        reward_max=1.0,
        max_steps=4,
        safety_constraint_refs=("policy:local-only", "policy:no-authority-amplification"),
    )
    learning.register_environment(environment)
    episode = learning.record_episode(
        episode_id="p3-t2-episode-1",
        environment_id=environment.environment_id,
        policy_digest=run.artifact.model_digest,
        seed=42,
        rewards=(0.5, 0.5),
        terminated=True,
        observations_digest=_sha("t2-observations"),
        actions_digest=_sha("t2-actions"),
    )
    stage = learning.evaluate_stage(
        CurriculumStage(
            stage_id="p3-t2-stage-1",
            environment_id=environment.environment_id,
            minimum_mean_reward=1.0,
            required_episodes=1,
            maximum_failure_rate=0.0,
        ),
        episode_ids=(episode.episode_id,),
    )
    assert stage.passed is True
    verifier = learning.evaluate_verifier_candidate(
        VerifierCandidate(
            candidate_id="p3-t2-verifier-candidate",
            model_digest=run.artifact.model_digest,
            training_receipt_digest=run.receipt.digest,
            benchmark_refs=("benchmark:p3-t2-heldout",),
            intended_claims=("claim:bounded-local-learning",),
        ),
        verifier_id="p3-t2-independent-model-verifier",
        trainer_id=run.receipt.trainer_id,
        evaluation_refs=("eval:training-gate", "eval:curriculum-gate"),
        curriculum_decision_refs=(stage.decision_digest,),
    )
    assert verifier.passed is True

    multimodal = MultimodalCorpus()
    record = multimodal.ingest(
        record_id="p3-t2-doc",
        modality=LearningModality.DOCUMENT,
        media_type="text/plain",
        payload=b"Local learning acceptance preserves provenance.",
        source_refs=(train.identity,),
        rights_refs=train.rights_refs,
        lineage_refs=(run.receipt.digest, verifier.decision_digest),
        extracted_text="Local learning acceptance preserves provenance",
        extractor_ref="extractor:local-text-v1",
        language="en",
    )
    hits = multimodal.search("learning provenance")
    assert [hit.record_id for hit in hits] == [record.record_id]
    assert hits[0].record_digest == record.digest
    assert hits[0].source_refs == (train.identity,)

    # The complete acceptance chain is local and content-addressed.
    assert len(run.artifact.model_digest) == 64
    assert len(run.checkpoint.content_digest) == 64
    assert len(verifier.decision_digest) == 64
    assert len(record.digest) == 64

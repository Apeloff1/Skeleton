"""Assembled local training/reload, measured parity and reversible lifecycle."""

import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime

import pytest

from skeleton.ai.runtime.learning_foundation import (
    MigrationParityCase,
    ModelBillOfMaterials,
    ModelLifecycleError,
    ModelLifecycleRegistry,
    ModelLifecycleState,
)
from skeleton.ai.runtime.training import (
    DataQualityReport,
    DataQualityRule,
    DatasetManifest,
    DatasetRegistry,
    DatasetSplit,
    EvaluationCase,
    EvaluationHarness,
    EvaluationSuite,
    IngestEnvelope,
    ReferenceLocalTrainer,
    TrainingRepository,
    TrainingRunManifest,
    corpus_digest,
)

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@pytest.mark.asyncio
async def test_durable_native_artifacts_feed_measured_migration_and_exact_rollback(tmp_path):
    corpus = ("two plus two four", "three plus three six")
    datasets = DatasetRegistry(tmp_path / "datasets.sqlite3")
    ingest = IngestEnvelope.from_bytes(
        source_id="fixture://licensed-arithmetic",
        payload="\n".join(corpus).encode(),
        parser_version="plain@1",
        classification="internal",
        rights=("training", "evaluation"),
        trusted=True,
        acquired_at=NOW,
    )
    datasets.register_ingest(ingest)
    dataset = DatasetManifest(
        dataset_id="licensed-arithmetic",
        version="1",
        splits=(DatasetSplit("train", corpus_digest(corpus), len(corpus)),),
        source_ingest_digests=(ingest.content_digest,),
        classification="internal",
        permitted_uses=("training", "evaluation"),
        retention_class="model-development",
        parser_versions=("plain@1",),
    )
    datasets.register_dataset(dataset)
    datasets.record_quality(
        DataQualityReport.evaluate(
            dataset.digest,
            (DataQualityRule("validity", "valid_fraction", ">=", 1.0),),
            {"valid_fraction": 1.0},
        )
    )
    source_manifest = TrainingRunManifest(
        run_id="source",
        dataset_digest=dataset.digest,
        base_model_digest=_digest("empty-counts"),
        code_digest=_digest("reference-trainer-code"),
        environment_digest=_digest("local-environment"),
        hyperparameters={"order": 2},
        seed=0,
        resource_budget={"max_steps": 10, "max_documents": 2},
    )
    target_manifest = replace(source_manifest, run_id="target", seed=7)
    run_path = tmp_path / "training.sqlite3"
    runs = TrainingRepository(run_path)
    trained = {}
    for manifest in (source_manifest, target_manifest):
        model, artifact = ReferenceLocalTrainer(datasets, runs).train(manifest, corpus, now=NOW)
        assert runs.state(manifest.run_id) == "completed"
        trained[manifest.run_id] = (model, artifact)
    runs.close()

    reopened = TrainingRepository(run_path)
    lifecycle = ModelLifecycleRegistry()
    reloaded = {}
    for manifest in (source_manifest, target_manifest):
        # Completed retry must load from durable model counts without retraining.
        model, artifact = ReferenceLocalTrainer(datasets, reopened).train(manifest, corpus, now=NOW)
        assert artifact == trained[manifest.run_id][1]
        assert model.to_dict() == trained[manifest.run_id][0].to_dict()
        reloaded[manifest.run_id] = model
        mbom = ModelBillOfMaterials(
            model_id=model.model_id,
            model_digest=model.model_digest,
            artifact_digest=_digest(model.to_dict()),
            artifact_kind="reference_ngram",
            training_run_id=artifact.run_id,
            training_receipt_digest=_digest(asdict(artifact)),
            dataset_digests=(artifact.dataset_digest,),
            trainer_id="reference-local-trainer",
            code_revision=manifest.code_digest,
            license_refs=("license:arithmetic-fixture",),
            rights_refs=("rights:training", "rights:evaluation"),
            dependency_refs=("checkpoint:" + artifact.checkpoint_digest,),
        )
        lifecycle.register_candidate(mbom)
        lifecycle.transition(
            model.model_digest,
            ModelLifecycleState.VALIDATED,
            verifier_id="independent-lifecycle-reviewer",
            evidence_refs=("training:" + artifact.checkpoint_digest, "dataset:" + dataset.digest),
        )

    source, target = reloaded["source"], reloaded["target"]
    lifecycle.transition(
        source.model_digest,
        ModelLifecycleState.ACTIVE,
        verifier_id="independent-lifecycle-reviewer",
        evidence_refs=("review:local-source", "rollout:isolated-fixture"),
    )
    suite = EvaluationSuite(
        suite_id="arithmetic-parity",
        version="1",
        cases=(
            EvaluationCase("two", "two plus two", "four", 1),
            EvaluationCase("three", "three plus three", "six", 1),
        ),
        population="controlled-parity-fixture",
        contamination_fingerprint=_digest("controlled-parity-fixture@1"),
    )
    source_result = await EvaluationHarness().evaluate(source, suite)
    target_result = await EvaluationHarness().evaluate(target, suite)
    assert source_result.accuracy == target_result.accuracy == 1.0
    cases = tuple(
        MigrationParityCase(
            case.case_id,
            _digest(case.as_dict()),
            _digest(source_result.outputs[case.case_id]),
            _digest(target_result.outputs[case.case_id]),
        )
        for case in suite.cases
    )
    decision = lifecycle.evaluate_migration(
        source_model_digest=source.model_digest,
        target_model_digest=target.model_digest,
        cases=cases,
        required_score=1.0,
        verifier_id="independent-parity-observer",
        evaluation_refs=(source_result.digest, target_result.digest),
    )
    assert decision.approved
    migration = lifecycle.apply_migration(decision)
    assert lifecycle.state(target.model_digest) == ModelLifecycleState.ACTIVE
    assert lifecycle.state(source.model_digest) == ModelLifecycleState.DEPRECATED
    assert lifecycle.apply_migration(decision) == migration
    rollback = lifecycle.rollback_migration(
        migration,
        verifier_id="independent-parity-observer",
        evidence_refs=("local-rollout:withdraw", "baseline:" + source.model_digest),
    )
    assert rollback.restored_model_digest == source.model_digest
    assert lifecycle.state(source.model_digest) == ModelLifecycleState.ACTIVE
    assert lifecycle.state(target.model_digest) == ModelLifecycleState.VALIDATED
    with pytest.raises(ModelLifecycleError, match="issued|identity|digest"):
        lifecycle.apply_migration(replace(decision, decision_digest=_digest("forged")))
    reopened.close()
    datasets.close()

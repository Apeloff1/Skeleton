"""Real governed media evidence through SGD, restart, parity and rollback."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from datetime import UTC, datetime

import numpy as np
import pytest
from PIL import Image

from skeleton.ai.runtime.learning_foundation.lifecycle import (
    MigrationParityCase,
    ModelBillOfMaterials,
    ModelLifecycleRegistry,
    ModelLifecycleState,
)
from skeleton.ai.runtime.learning_foundation.multimodal import (
    LearningModality,
    MultimodalCorpus,
)
from skeleton.ai.runtime.training.control import TrainingRepository, TrainingRunManifest
from skeleton.ai.runtime.training.data import (
    DataQualityReport,
    DataQualityRule,
    DatasetRegistry,
)
from skeleton.ai.runtime.training.evaluation import (
    EvaluationCase,
    EvaluationHarness,
    EvaluationSuite,
)
from skeleton.ai.runtime.training.neural_trainer import NeuralLocalTrainer
from skeleton.ai.runtime.training.trainer import ReferenceLocalTrainer

NOW = datetime(2026, 10, 4, tzinfo=UTC)
NEURAL_CONFIG = {"hidden_size": 4, "epochs": 8, "learning_rate": 1.0, "gradient_clip": 5.0, "now": NOW}


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def _media(corpus, record_id, text, *, image=False):
    payload = text.encode("utf-8")
    if image:
        output = io.BytesIO()
        color = tuple(hashlib.sha256(record_id.encode()).digest()[:3])
        Image.new("RGB", (2, 2), color).save(output, format="PNG")
        payload = output.getvalue()
    return corpus.ingest(
        record_id=record_id,
        modality=LearningModality.IMAGE if image else LearningModality.DOCUMENT,
        media_type="image/png" if image else "text/plain",
        payload=payload,
        source_refs=(f"source:{record_id}",),
        rights_refs=("rights:licensed-model-development",),
        lineage_refs=(f"lineage:acquisition:{record_id}",),
        extracted_text=text,
        extractor_ref="extractor:ocr-v1" if image else "extractor:text-v1",
        language="en",
        verified=image,
    )


def _export(corpus, record_ids, purpose):
    return corpus.export_text_training(
        record_ids,
        export_id=f"export:{purpose}",
        purpose=purpose,
        rights_policy={"rights:licensed-model-development": ("training", "evaluation")},
        max_documents=2,
        max_document_bytes=32,
        max_total_bytes=64,
    )


def _neural_manifest(run_id, dataset_digest):
    initial = NeuralLocalTrainer.initialize_model(run_id, hidden_size=4, seed=13)
    return TrainingRunManifest(
        run_id=run_id,
        dataset_digest=dataset_digest,
        base_model_digest=initial.model_digest,
        code_digest=_digest("native-neural-sgd@1"),
        environment_digest=_digest("numpy-local-reference@1"),
        hyperparameters={"hidden_size": 4, "epochs": 8, "learning_rate": 1.0, "gradient_clip": 5.0},
        seed=13,
        resource_budget={
            "max_steps": 304,
            "max_documents": 16,
            "max_updates": 16,
            "max_epochs": 8,
            "max_corpus_bytes": 64,
            "max_training_bytes": 288,
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("source_lifecycle", ("revoke", "delete", "failed_quality", "corrupt_bytes"))
async def test_governed_multimodal_sgd_parity_rollback_and_source_retirement(tmp_path, source_lifecycle):
    media = MultimodalCorpus()
    train_records = (
        _media(media, "licensed-document", "a" * 16),
        _media(media, "licensed-image", "a" * 20, image=True),
    )
    _media(media, "heldout-short", "a")
    _media(media, "heldout-long", "aaa", image=True)
    export, training_documents = _export(
        media, tuple(record.record_id for record in train_records), "training"
    )
    heldout_export, heldout_documents = _export(media, ("heldout-short", "heldout-long"), "evaluation")
    assert {sample.asset_digest for sample in export.samples}.isdisjoint(
        sample.asset_digest for sample in heldout_export.samples
    )
    assert {sample.text_digest for sample in export.samples}.isdisjoint(
        sample.text_digest for sample in heldout_export.samples
    )

    data_path = tmp_path / "governed-data.sqlite3"
    run_path = tmp_path / "sgd-runs.sqlite3"
    lifecycle_path = tmp_path / "candidate-lifecycle.sqlite3"
    datasets = DatasetRegistry(data_path)
    materialized = datasets.ingest_export(
        export, training_documents, dataset_id="licensed-media", acquired_at=NOW
    )
    evaluation_data = datasets.ingest_export(
        heldout_export, heldout_documents, dataset_id="heldout-media", acquired_at=NOW
    )
    assert datasets.training_corpus(materialized.dataset_digest) == training_documents
    assert datasets.latest_quality(materialized.dataset_digest).digest == materialized.quality_report_digest
    assert datasets.latest_quality(materialized.dataset_digest).passed
    manifests = tuple(
        _neural_manifest(run_id, materialized.dataset_digest) for run_id in ("source", "target")
    )
    native_manifest = TrainingRunManifest(
        run_id="reference-baseline",
        dataset_digest=materialized.dataset_digest,
        base_model_digest=_digest("reference-empty-counts"),
        code_digest=_digest("reference-count-estimator@1"),
        environment_digest=_digest("local-environment@1"),
        hyperparameters={"order": 2},
        seed=0,
        resource_budget={"max_steps": 4, "max_documents": 2},
    )
    runs = TrainingRepository(run_path)
    trained = {}
    initial_weights = {}
    for manifest in manifests:
        initial_weights[manifest.run_id] = NeuralLocalTrainer.initialize_model(
            manifest.run_id, hidden_size=4, seed=13
        ).to_dict()
        model, artifact = NeuralLocalTrainer(datasets, runs).train(
            manifest, training_documents, **NEURAL_CONFIG
        )
        assert artifact.update_count == 16
        assert artifact.token_count == 304
        assert artifact.training_bytes == 288
        assert artifact.final_loss < artifact.initial_loss
        assert artifact.initial_model_digest == manifest.base_model_digest
        assert model.model_digest != artifact.initial_model_digest
        assert runs.state(manifest.run_id) == "completed"
        assert not np.array_equal(model.output, initial_weights[manifest.run_id]["parameters"]["output"])
        trained[manifest.run_id] = (model.to_dict(), artifact)
    _, native_artifact = ReferenceLocalTrainer(datasets, runs).train(
        native_manifest, training_documents, now=NOW
    )
    runs.close()
    datasets.close()

    # Restore canonical source bytes and checkpoints before using any models.
    datasets = DatasetRegistry(data_path)
    runs = TrainingRepository(run_path)
    restored_documents = datasets.training_corpus(materialized.dataset_digest)
    assert restored_documents == training_documents
    sources = datasets.materialized_sources(materialized.dataset_digest)
    assert len(sources) == 1
    source = sources[0]
    assert source.documents() == training_documents
    assert source.evidence["multimodal_manifest"] == export.as_dict()
    assert source.evidence["multimodal_manifest_digest"] == export.digest
    assert source.rights_refs == ("rights:licensed-model-development",)
    assert set(source.lineage_refs).issuperset(
        reference for record in train_records for reference in record.lineage_refs
    )
    for recorded, original in zip(
        source.evidence["multimodal_manifest"]["samples"], train_records, strict=True
    ):
        assert recorded["record_digest"] == original.digest
        assert recorded["asset_digest"] == original.asset_digest
        assert recorded["projection_digest"] == original.text_projection.digest
        assert recorded["instruction_trusted"] is False
    assert datasets.materialized_sources(evaluation_data.dataset_digest)[0].documents() == heldout_documents
    with pytest.raises(PermissionError, match="not permitted for training"):
        datasets.training_corpus(evaluation_data.dataset_digest)

    reloaded = {}
    registry = ModelLifecycleRegistry(path=lifecycle_path)
    for manifest in manifests:
        model, artifact = NeuralLocalTrainer(datasets, runs).load_artifact(manifest.run_id)
        assert artifact == trained[manifest.run_id][1]
        assert model.to_dict() == trained[manifest.run_id][0]
        assert artifact.dataset_digest == materialized.dataset_digest
        reloaded[manifest.run_id] = model
        registry.register_candidate(
            ModelBillOfMaterials(
                model_id=model.model_id,
                model_digest=model.model_digest,
                artifact_digest=_digest(model.to_dict()),
                artifact_kind="numpy_recurrent_byte_lm",
                training_run_id=manifest.run_id,
                training_receipt_digest=artifact.training_receipt_digest,
                dataset_digests=(materialized.dataset_digest,),
                trainer_id="numpy-recurrent-byte-sgd-v1",
                code_revision=manifest.code_digest,
                license_refs=("license:controlled-media-fixture",),
                rights_refs=source.rights_refs,
                dependency_refs=(f"checkpoint:{artifact.checkpoint_digest}", f"export:{export.digest}"),
            )
        )
    _, restored_native = ReferenceLocalTrainer(datasets, runs).train(
        native_manifest, restored_documents, now=NOW
    )
    assert restored_native == native_artifact

    suite = EvaluationSuite(
        suite_id="heldout-byte-continuation",
        version="1",
        cases=tuple(
            EvaluationCase(f"heldout-{index}", prompt, "a", 1)
            for index, prompt in enumerate(heldout_documents)
        ),
        population="isolated-controlled-byte-fixture",
        contamination_fingerprint=heldout_export.document_sequence_digest,
    )
    results = {}
    for manifest in manifests:
        model = reloaded[manifest.run_id]
        result = await EvaluationHarness().evaluate(model, suite, seed=0)
        assert result.candidate_model_digest == model.model_digest
        assert result.accuracy == 1.0
        assert result.outputs == {"heldout-0": "a", "heldout-1": "a"}
        results[manifest.run_id] = result
        registry.transition(
            model.model_digest,
            ModelLifecycleState.VALIDATED,
            verifier_id="independent-heldout-evaluator",
            evidence_refs=(
                f"evaluation:{result.digest}",
                f"heldout-dataset:{evaluation_data.dataset_digest}",
            ),
        )
    source_model, target_model = reloaded["source"], reloaded["target"]
    registry.transition(
        source_model.model_digest,
        ModelLifecycleState.ACTIVE,
        verifier_id="independent-lifecycle-controller",
        evidence_refs=(f"source-evaluation:{results['source'].digest}", "rollback:retain-source-artifact"),
    )
    parity_cases = tuple(
        MigrationParityCase(
            case_id=case.case_id,
            input_digest=_digest(case.as_dict()),
            source_output_digest=_digest(results["source"].outputs[case.case_id]),
            target_output_digest=_digest(results["target"].outputs[case.case_id]),
        )
        for case in suite.cases
    )
    decision = registry.evaluate_migration(
        source_model_digest=source_model.model_digest,
        target_model_digest=target_model.model_digest,
        cases=parity_cases,
        required_score=1.0,
        verifier_id="independent-measured-parity",
        evaluation_refs=(results["source"].digest, results["target"].digest),
    )
    assert decision.approved
    assert decision.parity_score == 1.0
    migration = registry.apply_migration(decision)
    assert registry.state(source_model.model_digest) == ModelLifecycleState.DEPRECATED
    assert registry.state(target_model.model_digest) == ModelLifecycleState.ACTIVE

    # The lifecycle repository opens/closes each transaction connection.
    del registry
    registry = ModelLifecycleRegistry(path=lifecycle_path)
    recovered_decision = registry.decision(decision.decision_digest)
    history = registry.history
    assert registry.apply_migration(recovered_decision) == migration
    assert registry.history == history
    assert registry.migrations == (migration,)
    rollback = registry.rollback_migration(
        registry.migrations[0],
        verifier_id="independent-rollback-controller",
        evidence_refs=(f"migration:{migration.receipt_digest}", f"restore:{source_model.model_digest}"),
    )
    del registry
    registry = ModelLifecycleRegistry(path=lifecycle_path)
    assert registry.rollbacks == (rollback,)
    assert registry.state(source_model.model_digest) == ModelLifecycleState.ACTIVE
    assert registry.state(target_model.model_digest) == ModelLifecycleState.VALIDATED

    source_content_digest = materialized.manifest.source_ingest_digests[0]
    denial = (PermissionError,)
    reason = "revoked|deleted|authority"
    if source_lifecycle == "revoke":
        datasets.revoke_source_rights(
            source_content_digest,
            uses=("training",),
            reason="licensed use withdrawn",
            command_id="revoke:source",
        )
    elif source_lifecycle == "delete":
        datasets.delete_source(
            source_content_digest, reason="source retention ended", command_id="delete:source"
        )
    elif source_lifecycle == "failed_quality":
        previous_quality = datasets.latest_quality(materialized.dataset_digest)
        datasets.record_quality(
            DataQualityReport.evaluate(
                materialized.dataset_digest,
                (*previous_quality.rules, DataQualityRule("hold.latest_policy", "record_count", "<", 0.0)),
                previous_quality.metrics,
                observation_digest=previous_quality.observation_digest,
                split_sequence_digests=previous_quality.split_sequence_digests,
            )
        )
        denial = (PermissionError, RuntimeError)
        reason = "quality|authority"
    else:
        # A damaged restored blob must invalidate current evidence admission even
        # though its authority epoch and the previously learned weights survive.
        with sqlite3.connect(data_path) as connection:
            connection.execute(
                "UPDATE materialized_source SET payload=? WHERE content_digest=?",
                (b"corrupt restored source", source_content_digest),
            )
        denial = (ValueError,)
        reason = "content|integrity|materialized"
    datasets.close()
    datasets = DatasetRegistry(data_path)
    checkpoints = {
        manifest.run_id: runs.latest_checkpoint(manifest.run_id).digest
        for manifest in (*manifests, native_manifest)
    }
    with pytest.raises(denial, match=reason):
        datasets.training_corpus(materialized.dataset_digest)
    for manifest in manifests:
        with pytest.raises(denial, match=reason):
            NeuralLocalTrainer(datasets, runs).train(manifest, training_documents, **NEURAL_CONFIG)
        with pytest.raises(denial, match=reason):
            NeuralLocalTrainer(datasets, runs).load_artifact(manifest.run_id)
    with pytest.raises(denial, match=reason):
        ReferenceLocalTrainer(datasets, runs).train(native_manifest, training_documents, now=NOW)
    for manifest in (*manifests, native_manifest):
        assert runs.state(manifest.run_id) == "completed"
        assert runs.latest_checkpoint(manifest.run_id).digest == checkpoints[manifest.run_id]
    assert registry.state(source_model.model_digest) == ModelLifecycleState.ACTIVE
    assert registry.state(target_model.model_digest) == ModelLifecycleState.VALIDATED
    runs.close()
    datasets.close()

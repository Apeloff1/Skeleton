from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from skeleton.ai.runtime.inference import (
    LocalInferenceCancelled,
    LocalInferenceEngine,
    LocalInferenceRequest,
)
from skeleton.ai.runtime.inference.neural import NumpyRecurrentLM
from skeleton.ai.runtime.training import (
    DataQualityReport,
    DataQualityRule,
    DatasetManifest,
    DatasetRegistry,
    DatasetSplit,
    IngestEnvelope,
    TrainingRepository,
    TrainingRunManifest,
    TrainingStateError,
    corpus_digest,
)
from skeleton.ai.runtime.training.data import MaterializedTrainingSource
from skeleton.ai.runtime.training.neural_trainer import NeuralLocalTrainer

NOW = datetime(2026, 10, 4, 16, tzinfo=UTC)
CORPUS = ("aba", "abc", "café")
TRAIN_KWARGS = {"hidden_size": 8, "epochs": 3, "learning_rate": 0.1, "gradient_clip": 1.0, "now": NOW}


class AbruptStop(BaseException):
    pass


def test_neural_inference_interrupts_during_input_priming():
    class CancelDuringPriming(threading.Event):
        polls = 0

        def is_set(self):
            self.polls += 1
            if self.polls == 5:
                self.set()
            return super().is_set()

    model = NeuralLocalTrainer.initialize_model("bounded-prime", hidden_size=4, seed=1)
    digest = model.model_digest
    cancellation = CancelDuringPriming()
    with pytest.raises(LocalInferenceCancelled, match="input priming"):
        model.infer(LocalInferenceRequest(prompt="a" * 100000, max_output_tokens=2), cancellation)
    assert cancellation.polls == 5
    assert model.model_digest == digest


def test_neural_pre_cancelled_inference_avoids_prompt_encoding(monkeypatch):
    from skeleton.ai.runtime.inference import neural

    model = NeuralLocalTrainer.initialize_model("cancel-before-prime", hidden_size=4, seed=1)
    cancellation = threading.Event()
    cancellation.set()

    def forbidden(*args, **kwargs):
        raise AssertionError("cancelled model must not allocate prompt tokens")

    monkeypatch.setattr(neural, "_encode", forbidden)
    with pytest.raises(LocalInferenceCancelled):
        model.infer(LocalInferenceRequest(prompt="bounded", max_output_tokens=2), cancellation)


def _fixture(tmp_path, *, corpus=CORPUS, budget=None):
    datasets = DatasetRegistry(tmp_path / "datasets.sqlite3")
    ingest = IngestEnvelope.from_bytes(
        source_id="fixture://neural-corpus",
        payload="\n".join(corpus).encode(),
        parser_version="plain@1",
        classification="internal",
        rights=("training",),
        trusted=True,
        acquired_at=NOW,
    )
    datasets.register_ingest(ingest)
    dataset = DatasetManifest(
        dataset_id="neural-corpus",
        version="1",
        splits=(
            DatasetSplit("train", corpus_digest(corpus), len(corpus)),
            DatasetSplit("alternate", corpus_digest(corpus), len(corpus)),
        ),
        source_ingest_digests=(ingest.content_digest,),
        classification="internal",
        permitted_uses=("training",),
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
    initial = NeuralLocalTrainer.initialize_model("neural-run", hidden_size=8, seed=13)
    run = TrainingRunManifest(
        run_id="neural-run",
        dataset_digest=dataset.digest,
        base_model_digest=initial.model_digest,
        code_digest=hashlib.sha256(b"neural-code").hexdigest(),
        environment_digest=hashlib.sha256(b"numpy-float64").hexdigest(),
        hyperparameters={},
        seed=13,
        resource_budget=budget
        or {"max_steps": 3 * sum(len(item.encode()) + 1 for item in corpus), "max_updates": 3 * len(corpus)},
    )
    return datasets, TrainingRepository(tmp_path / "runs.sqlite3"), run, initial


@pytest.mark.parametrize("error, state", [(AbruptStop, "running"), (RuntimeError, "failed")])
def test_real_neural_resume_inside_epoch_matches_uninterrupted_weights_without_replay(
    tmp_path, monkeypatch, error, state
):
    datasets, runs, run, expected = _fixture(tmp_path)
    receipt = expected.train(CORPUS, epochs=3, learning_rate=0.1, gradient_clip=1.0)
    real_update = NumpyRecurrentLM.train_document
    calls = []

    def interrupted(self, document, **kwargs):
        calls.append(document)
        if len(calls) == 5:
            raise error("interrupt second epoch")
        return real_update(self, document, **kwargs)

    monkeypatch.setattr(NumpyRecurrentLM, "train_document", interrupted)
    with pytest.raises(error, match="second epoch"):
        NeuralLocalTrainer(datasets, runs).train(run, CORPUS, **TRAIN_KWARGS)
    checkpoint = runs.latest_checkpoint(run.run_id)
    assert runs.state(run.run_id) == state
    payload = runs.checkpoint_payload(checkpoint)
    assert payload["cursor"] == {"epoch": 1, "document_index": 1, "update_count": 4, "step": 18}
    runs.close()
    reopened = TrainingRepository(tmp_path / "runs.sqlite3")
    resumed_calls = []

    def resumed(self, document, **kwargs):
        resumed_calls.append(document)
        return real_update(self, document, **kwargs)

    monkeypatch.setattr(NumpyRecurrentLM, "train_document", resumed)
    model, artifact = NeuralLocalTrainer(datasets, reopened).train(run, CORPUS, **TRAIN_KWARGS)
    assert resumed_calls == ["abc", "café", "aba", "abc", "café"]
    assert model.model_digest == expected.model_digest
    for name in ("embedding", "recurrent", "hidden_bias", "output", "output_bias"):
        np.testing.assert_array_equal(getattr(model, name), getattr(expected, name))
    assert artifact.initial_loss == receipt.initial_loss
    assert artifact.final_loss == receipt.final_loss < artifact.initial_loss
    assert artifact.token_count == 42 and artifact.update_count == 9
    assert artifact.training_bytes == 33
    assert reopened.latest_checkpoint(run.run_id).worker_epoch == checkpoint.worker_epoch + 1


def test_neural_model_reload_and_completed_retry_do_not_update_or_write(tmp_path, monkeypatch):
    datasets, runs, run, _ = _fixture(tmp_path)
    model, artifact = NeuralLocalTrainer(datasets, runs).train(run, CORPUS, **TRAIN_KWARGS)
    runs.close()
    reopened = TrainingRepository(tmp_path / "runs.sqlite3")

    def unexpected(*args, **kwargs):
        raise AssertionError("completed neural run cannot update weights")

    monkeypatch.setattr(NumpyRecurrentLM, "train_document", unexpected)
    trainer = NeuralLocalTrainer(datasets, reopened)
    before = reopened._db.total_changes
    loaded, loaded_artifact = trainer.load_artifact(run.run_id)
    retried, retried_artifact = trainer.train(run, CORPUS, **TRAIN_KWARGS)
    assert loaded.to_dict() == retried.to_dict() == model.to_dict()
    assert loaded_artifact == retried_artifact == artifact
    assert reopened._db.total_changes == before


@pytest.mark.parametrize("point", ["initial", "terminal"])
def test_neural_recovers_crash_at_initial_or_terminal_checkpoint(tmp_path, monkeypatch, point):
    datasets, runs, run, expected = _fixture(tmp_path)
    expected.train(CORPUS, epochs=3, learning_rate=0.1)

    def stop(*args, **kwargs):
        raise AbruptStop("checkpoint window")

    monkeypatch.setattr(runs, "checkpoint" if point == "initial" else "complete", stop)
    with pytest.raises(AbruptStop, match="checkpoint window"):
        NeuralLocalTrainer(datasets, runs).train(run, CORPUS, **TRAIN_KWARGS)
    assert (runs.latest_checkpoint(run.run_id) is None) is (point == "initial")
    runs.close()
    reopened = TrainingRepository(tmp_path / "runs.sqlite3")
    if point == "terminal":
        monkeypatch.setattr(NumpyRecurrentLM, "train_document", stop)
    model, artifact = NeuralLocalTrainer(datasets, reopened).train(run, CORPUS, **TRAIN_KWARGS)
    assert model.model_digest == expected.model_digest
    assert artifact.final_loss < artifact.initial_loss


@pytest.mark.parametrize(
    "field,value",
    [
        ("learning_rate", 0.2),
        ("gradient_clip", 2.0),
        ("epochs", 4),
        ("hidden_size", 12),
        ("split_name", "alternate"),
    ],
)
def test_neural_configuration_retry_cannot_change_training_identity(tmp_path, field, value, monkeypatch):
    datasets, runs, run, _ = _fixture(tmp_path, budget={"max_steps": 1000, "max_updates": 100})
    NeuralLocalTrainer(datasets, runs).train(run, CORPUS, **TRAIN_KWARGS)

    def unexpected(*args, **kwargs):
        raise AssertionError("conflicting neural retry must fail before SGD")

    monkeypatch.setattr(NumpyRecurrentLM, "train_document", unexpected)
    kwargs = {**TRAIN_KWARGS, field: value}
    with pytest.raises(TrainingStateError, match="immutable|base model digest"):
        NeuralLocalTrainer(datasets, runs).train(run, CORPUS, **kwargs)
    assert runs.state(run.run_id) == "completed"


@pytest.mark.parametrize(
    "budget",
    [
        {"max_steps": 1},
        {"max_tokens": 41},
        {"max_updates": 8},
        {"max_documents": 8},
        {"max_training_bytes": 32},
        {"max_epochs": 2},
        {"max_corpus_bytes": 12},
    ],
)
def test_neural_cumulative_epoch_budgets_admit_before_model_updates(tmp_path, budget, monkeypatch):
    datasets, runs, run, _ = _fixture(tmp_path, budget=budget)

    def unexpected(*args, **kwargs):
        raise AssertionError("budget check must precede SGD allocation")

    monkeypatch.setattr(NumpyRecurrentLM, "train_document", unexpected)
    with pytest.raises(TrainingStateError, match="budget exceeded"):
        NeuralLocalTrainer(datasets, runs).train(run, CORPUS, **TRAIN_KWARGS)
    with pytest.raises(KeyError):
        runs.state(run.run_id)


@pytest.mark.parametrize("target", ["payload", "binding", "model", "missing"])
def test_neural_checkpoint_tamper_prevents_model_reload(tmp_path, target):
    datasets, runs, run, _ = _fixture(tmp_path)
    NeuralLocalTrainer(datasets, runs).train(run, CORPUS, **TRAIN_KWARGS)
    checkpoint = runs.latest_checkpoint(run.run_id)
    if target == "binding":
        runs._db.execute("UPDATE training_execution_binding SET binding_json='{}'")
    elif target == "missing":
        runs._db.execute(
            "DELETE FROM training_checkpoint_payload WHERE checkpoint_digest=?", (checkpoint.digest,)
        )
    else:
        payload = runs.checkpoint_payload(checkpoint)
        if target == "model":
            payload["model"]["parameters"]["embedding"][0][0] += 1.0
        else:
            payload["optimizer"]["learning_rate"] = 9.0
        runs._db.execute(
            "UPDATE training_checkpoint_payload SET payload_json=? WHERE checkpoint_digest=?",
            (json.dumps(payload), checkpoint.digest),
        )
    runs._db.commit()
    runs.close()
    reopened = TrainingRepository(tmp_path / "runs.sqlite3")
    with pytest.raises(TrainingStateError, match="identity mismatch|missing"):
        NeuralLocalTrainer(datasets, reopened).load_artifact(run.run_id)


def test_neural_stale_worker_cannot_publish_or_fail_replacement_run(tmp_path, monkeypatch):
    datasets, runs, run, _ = _fixture(tmp_path)
    other = TrainingRepository(tmp_path / "runs.sqlite3")
    real_update = NumpyRecurrentLM.train_document
    replaced = False

    def update_after_replacement(self, document, **kwargs):
        nonlocal replaced
        if not replaced:
            replaced = True
            other.recover(run.run_id)
            other.start(run.run_id)
            other.lease_worker(run.run_id, "replacement", issued_at=NOW)
        return real_update(self, document, **kwargs)

    monkeypatch.setattr(NumpyRecurrentLM, "train_document", update_after_replacement)
    with pytest.raises(TrainingStateError, match="stale worker epoch"):
        NeuralLocalTrainer(datasets, runs).train(run, CORPUS, **TRAIN_KWARGS)
    assert other.state(run.run_id) == "running"
    assert other.latest_checkpoint(run.run_id).step == 0


@pytest.mark.asyncio
async def test_trained_neural_weights_execute_through_local_inference(tmp_path):
    datasets, runs, run, _ = _fixture(tmp_path)
    model, artifact = NeuralLocalTrainer(datasets, runs).train(run, CORPUS, **TRAIN_KWARGS)
    response = await LocalInferenceEngine(model, cache_size=0).generate(
        LocalInferenceRequest(prompt="ab", max_output_tokens=4, seed=7)
    )
    assert response.model_digest == artifact.model_digest
    assert response.model_id == artifact.model_id
    assert response.text and response.output_tokens <= 4
    assert artifact.final_loss == model.loss(CORPUS) < artifact.initial_loss


def test_neural_rejects_unbound_base_model_before_registering_run(tmp_path):
    datasets, runs, run, _ = _fixture(tmp_path)
    drifted = replace(run, base_model_digest=hashlib.sha256(b"wrong base").hexdigest())
    with pytest.raises(TrainingStateError, match="base model digest"):
        NeuralLocalTrainer(datasets, runs).train(drifted, CORPUS, **TRAIN_KWARGS)
    with pytest.raises(KeyError):
        runs.state(run.run_id)


def test_single_document_update_matches_existing_multi_epoch_training_exactly():
    first = NeuralLocalTrainer.initialize_model("direct", hidden_size=8, seed=11)
    second = NeuralLocalTrainer.initialize_model("direct", hidden_size=8, seed=11)
    first.train(CORPUS, epochs=3, learning_rate=0.1, gradient_clip=1.0)
    for _ in range(3):
        for document in CORPUS:
            assert (
                second.train_document(document, learning_rate=0.1, gradient_clip=1.0)
                == len(document.encode()) + 1
            )
    assert second.to_dict() == first.to_dict()


def test_neural_machine_contract_matches_actual_binding_payload_and_optimizer_fields(tmp_path):
    datasets, runs, run, _ = _fixture(tmp_path)
    NeuralLocalTrainer(datasets, runs).train(run, CORPUS, **TRAIN_KWARGS)
    contract = json.loads(
        (Path(__file__).resolve().parents[2] / "machine/ai_neural_training_resume_contract.json").read_text()
    )
    binding = runs.execution_binding(run.run_id)
    payload = runs.checkpoint_payload(runs.latest_checkpoint(run.run_id))
    assert binding["schema_version"] == contract["binding"]["schema_version"]
    assert set(binding) - {"schema_version"} == set(contract["binding"]["immutable_fields"])
    assert set(binding["training_config"]) == set(contract["binding"]["training_config_fields"])
    assert payload["schema_version"] == contract["resume_payload"]["schema_version"]
    assert set(payload) == set(contract["resume_payload"]["fields"])
    for name in ("cursor", "usage", "optimizer"):
        assert set(payload[name]) == set(contract["resume_payload"][f"{name}_fields"])


def test_uncommitted_partial_neural_update_reloads_last_durable_weights(tmp_path, monkeypatch):
    datasets, runs, run, expected = _fixture(tmp_path)
    expected.train(CORPUS, epochs=3, learning_rate=0.1)
    real_update = NumpyRecurrentLM.train_document

    def crash_after_mutation(self, document, **kwargs):
        real_update(self, document, **kwargs)
        raise RuntimeError("parameters mutated before checkpoint")

    monkeypatch.setattr(NumpyRecurrentLM, "train_document", crash_after_mutation)
    with pytest.raises(RuntimeError, match="mutated before checkpoint"):
        NeuralLocalTrainer(datasets, runs).train(run, CORPUS, **TRAIN_KWARGS)
    assert runs.latest_checkpoint(run.run_id).model_digest == run.base_model_digest
    assert runs.latest_checkpoint(run.run_id).step == 0
    runs.close()
    monkeypatch.setattr(NumpyRecurrentLM, "train_document", real_update)
    reopened = TrainingRepository(tmp_path / "runs.sqlite3")
    resumed, _ = NeuralLocalTrainer(datasets, reopened).train(run, CORPUS, **TRAIN_KWARGS)
    assert resumed.to_dict() == expected.to_dict()


def _materialize(datasets, corpus):
    raw = json.dumps(list(corpus), ensure_ascii=False).encode()
    source = MaterializedTrainingSource(
        envelope=IngestEnvelope.from_bytes(
            source_id="fixture://materialized-neural",
            payload=raw,
            parser_version="json-documents@1",
            classification="internal",
            rights=("training",),
            trusted=True,
            acquired_at=NOW,
        ),
        payload=raw,
        format="json_documents",
        rights_refs=("rights:actual-fixture",),
    )
    receipt = datasets.ingest_materialized(
        ingestion_id="materialized-neural",
        dataset_id="actual-neural",
        expected_version=0,
        sources={"train": (source,)},
        classification="internal",
        permitted_uses=("training",),
        retention_class="model-development",
    )
    return receipt, source


def test_neural_trains_actual_materialized_rights_bound_dataset_and_reopens_both_authorities(tmp_path):
    datasets, runs, run, expected = _fixture(tmp_path)
    receipt, source = _materialize(datasets, CORPUS)
    corpus = datasets.training_corpus(receipt.dataset_digest)
    assert corpus == CORPUS
    run = replace(run, dataset_digest=receipt.dataset_digest)
    expected.train(CORPUS, epochs=3, learning_rate=0.1)
    model, artifact = NeuralLocalTrainer(datasets, runs).train(run, corpus, **TRAIN_KWARGS)
    assert model.model_digest == expected.model_digest
    assert artifact.dataset_digest == receipt.dataset_digest
    assert source.envelope.content_digest in receipt.manifest.source_ingest_digests
    runs.close()
    datasets.close()
    reopened_data = DatasetRegistry(tmp_path / "datasets.sqlite3")
    reopened_runs = TrainingRepository(tmp_path / "runs.sqlite3")
    reloaded, reloaded_artifact = NeuralLocalTrainer(reopened_data, reopened_runs).load_artifact(run.run_id)
    assert reloaded.to_dict() == model.to_dict() and reloaded_artifact == artifact


def test_materialized_neural_corpus_partition_drift_rejected_before_training(tmp_path):
    original, changed = ("a\nb", "c"), ("a", "b\nc")
    datasets, runs, run, _ = _fixture(tmp_path, corpus=original)
    receipt, _ = _materialize(datasets, original)
    run = replace(run, dataset_digest=receipt.dataset_digest)
    assert corpus_digest(original) == corpus_digest(changed)
    with pytest.raises(ValueError, match="identity|materialized|sequence"):
        NeuralLocalTrainer(datasets, runs).train(run, changed, **TRAIN_KWARGS)
    with pytest.raises(KeyError):
        runs.state(run.run_id)


@pytest.mark.parametrize("operation", ["revoke", "delete_source", "delete_dataset"])
def test_materialized_neural_artifact_rejects_revoked_or_deleted_source_authority_after_restart(
    tmp_path, operation
):
    datasets, runs, run, _ = _fixture(tmp_path)
    receipt, source = _materialize(datasets, CORPUS)
    run = replace(run, dataset_digest=receipt.dataset_digest)
    NeuralLocalTrainer(datasets, runs).train(run, CORPUS, **TRAIN_KWARGS)
    if operation == "revoke":
        datasets.revoke_source_rights(
            source.envelope.content_digest, reason="rights withdrawn", command_id="rights-1"
        )
    elif operation == "delete_source":
        datasets.delete_source(
            source.envelope.content_digest, reason="source removed", command_id="delete-source-1"
        )
    else:
        datasets.delete_dataset(
            receipt.dataset_digest, reason="dataset removed", command_id="delete-dataset-1"
        )
    datasets.close()
    runs.close()
    reopened_data = DatasetRegistry(tmp_path / "datasets.sqlite3")
    reopened_runs = TrainingRepository(tmp_path / "runs.sqlite3")
    with pytest.raises(PermissionError, match="revoked|deleted"):
        NeuralLocalTrainer(reopened_data, reopened_runs).load_artifact(run.run_id)
    assert reopened_runs.state(run.run_id) == "completed"


def test_rights_revoked_during_real_sgd_update_prevents_durable_checkpoint(tmp_path, monkeypatch):
    datasets, runs, run, _ = _fixture(tmp_path)
    receipt, source = _materialize(datasets, CORPUS)
    run = replace(run, dataset_digest=receipt.dataset_digest)
    real_update = NumpyRecurrentLM.train_document

    def update_and_revoke(self, document, **kwargs):
        observed = real_update(self, document, **kwargs)
        datasets.revoke_source_rights(
            source.envelope.content_digest,
            reason="rights withdrawn mid-update",
            command_id="mid-update-revoke",
        )
        return observed

    monkeypatch.setattr(NumpyRecurrentLM, "train_document", update_and_revoke)
    with pytest.raises(PermissionError, match="revoked"):
        NeuralLocalTrainer(datasets, runs).train(run, CORPUS, **TRAIN_KWARGS)
    assert runs.state(run.run_id) == "failed"
    assert runs.latest_checkpoint(run.run_id).step == 0
    assert runs.latest_checkpoint(run.run_id).model_digest == run.base_model_digest

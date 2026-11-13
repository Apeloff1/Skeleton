"""Restore admission rejects rehashed manifests outside each trainer's scope."""

from __future__ import annotations

import json
from dataclasses import replace
from skeleton.compat.datetime_utc import UTC
from datetime import datetime

import pytest

from skeleton.ai.runtime.training.checkpoint_archive import (
    CheckpointArchiveError,
    TrainingCheckpointArchive,
    _PayloadView,
)
from skeleton.ai.runtime.training.control import (
    TrainingRepository,
    TrainingRunManifest,
    TrainingStateError,
    _digest,
)
from skeleton.ai.runtime.training.data import (
    DatasetRegistry,
    IngestEnvelope,
    MaterializedTrainingSource,
)
from skeleton.ai.runtime.training.neural_trainer import NeuralLocalTrainer
from skeleton.ai.runtime.training.trainer import ReferenceLocalTrainer

NOW = datetime(2026, 10, 4, 18, tzinfo=UTC)
CORPUS = ("aba", "café")


def _fixture(path, algorithm):
    datasets = DatasetRegistry(path / "datasets.sqlite3")
    raw = json.dumps(list(CORPUS), ensure_ascii=False).encode()
    source = MaterializedTrainingSource(
        envelope=IngestEnvelope.from_bytes(
            source_id="fixture://restore-scope",
            payload=raw,
            parser_version="json-documents@1",
            classification="internal",
            rights=("training",),
            trusted=True,
            acquired_at=NOW,
        ),
        payload=raw,
        format="json_documents",
        rights_refs=("license:restore-scope",),
    )
    receipt = datasets.ingest_materialized(
        ingestion_id="scope-ingestion",
        dataset_id="scope-corpus",
        expected_version=0,
        sources={"train": (source,)},
        classification="internal",
        permitted_uses=("training",),
        retention_class="test",
    )
    runs = TrainingRepository(path / "training.sqlite3")
    trainer_class = NeuralLocalTrainer if algorithm == "neural" else ReferenceLocalTrainer
    base_digest = (
        NeuralLocalTrainer.initialize_model("scope-run", hidden_size=4, seed=7).model_digest
        if algorithm == "neural"
        else _digest("untrained-reference")
    )
    manifest = TrainingRunManifest(
        run_id="scope-run",
        dataset_digest=receipt.dataset_digest,
        base_model_digest=base_digest,
        code_digest=_digest("scope-fixture-code"),
        environment_digest=_digest("scope-fixture-runtime"),
        hyperparameters={},
        seed=7,
    )
    arguments = (
        {"hidden_size": 4, "epochs": 1} if algorithm == "neural" else {"checkpoint_every_documents": 1}
    )
    model, artifact = trainer_class(datasets, runs).train(manifest, CORPUS, now=NOW, **arguments)
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    binding = runs.execution_binding(manifest.run_id)
    payload = runs.checkpoint_payload(checkpoint)
    return datasets, runs, trainer_class, manifest, checkpoint, binding, payload, model, artifact


@pytest.mark.parametrize("algorithm", ["reference", "neural"])
@pytest.mark.parametrize(
    "world_size,parallelism",
    [(2, "single"), (1, "data_parallel"), (2, "data_parallel"), (1, "model_parallel"), (4, "hybrid")],
)
@pytest.mark.parametrize("validation", ["direct", "archive"])
def test_semantically_rehashed_out_of_scope_checkpoint_is_rejected_before_model_loading(
    tmp_path, monkeypatch, algorithm, world_size, parallelism, validation
):
    datasets, runs, trainer_class, manifest, checkpoint, binding, payload, model, _artifact = _fixture(
        tmp_path, algorithm
    )
    original_checkpoint = checkpoint
    original_binding = runs.execution_binding(manifest.run_id)
    original_payload = runs.checkpoint_payload(checkpoint)
    manifest = replace(manifest, world_size=world_size, parallelism=parallelism)
    binding["manifest_digest"] = manifest.digest
    payload["binding_digest"] = _digest(binding)
    checkpoint = replace(checkpoint, manifest_digest=manifest.digest, payload_digest=_digest(payload))
    assert checkpoint.manifest_digest == binding["manifest_digest"] == manifest.digest
    assert checkpoint.payload_digest == _digest(payload)
    assert payload["binding_digest"] == _digest(binding)
    assert checkpoint.model_digest == model.model_digest

    def forbidden(*args, **kwargs):
        raise AssertionError("out-of-scope restore must not decode learned weights")

    monkeypatch.setattr(type(model), "from_dict", forbidden)
    if validation == "direct":
        view = _PayloadView(checkpoint, payload)
        with pytest.raises(TrainingStateError, match="single|one worker|world_size"):
            trainer_class(datasets, view)._restore(manifest, binding, checkpoint, CORPUS)
    else:
        with pytest.raises(CheckpointArchiveError, match="compatibility"):
            TrainingCheckpointArchive._validate_model(
                datasets, manifest, binding, checkpoint, payload, CORPUS, runs
            )
    assert runs.latest_checkpoint(manifest.run_id) == original_checkpoint
    assert runs.execution_binding(manifest.run_id) == original_binding
    assert runs.checkpoint_payload(original_checkpoint) == original_payload
    assert runs.state(manifest.run_id) == "completed"


@pytest.mark.parametrize("algorithm", ["reference", "neural"])
def test_supported_single_worker_checkpoint_still_restores_and_validates_archive(tmp_path, algorithm):
    datasets, runs, trainer_class, manifest, checkpoint, binding, payload, model, artifact = _fixture(
        tmp_path, algorithm
    )
    view = _PayloadView(checkpoint, payload)
    restored = trainer_class(datasets, view)._restore(manifest, binding, checkpoint, CORPUS)
    assert restored[0].model_digest == model.model_digest
    TrainingCheckpointArchive._validate_model(datasets, manifest, binding, checkpoint, payload, CORPUS, runs)
    loaded, loaded_artifact = trainer_class(datasets, runs).load_artifact(manifest.run_id)
    assert loaded.model_digest == model.model_digest
    assert loaded_artifact == artifact

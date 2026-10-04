"""Operator CLI runs observed ingestion and real checkpoint-backed training."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from skeleton.ai.runtime.inference.artifact import load_local_model_artifact
from skeleton.ai.runtime.training.cli import (
    GovernedTrainingBuildError,
    _read_sources,
    build_governed_artifact,
    main,
)
from skeleton.ai.runtime.training.control import TrainingRepository
from skeleton.ai.runtime.training.data import DatasetRegistry
from skeleton.ai.runtime.training.trainer import ReferenceLocalTrainer


def _request(tmp_path, *, algorithm="reference"):
    source = tmp_path / "corpus.txt"
    source.write_text("two plus two four", encoding="utf-8")
    return {
        "corpus_paths": (source,),
        "state_directory": tmp_path / "state",
        "output_path": tmp_path / "model.json",
        "run_id": "operator-training",
        "dataset_id": "licensed-local-corpus",
        "rights_refs": ("license:operator-owned-fixture",),
        "algorithm": algorithm,
        "hidden_size": 8,
        "epochs": 2,
    }


def test_reference_cli_materializes_reloads_and_skips_completed_updates(tmp_path):
    request = _request(tmp_path)
    receipt = build_governed_artifact(**request)
    loaded = load_local_model_artifact(request["output_path"])
    assert receipt["model_digest"] == loaded.model.model_digest
    assert receipt["artifact"]["artifact_sha256"] == loaded.receipt.artifact_sha256
    datasets = DatasetRegistry(Path(request["state_directory"]) / "datasets.sqlite3")
    assert datasets.training_corpus(receipt["dataset_digest"]) == ("two plus two four",)
    datasets.close()
    request["output_path"].unlink()
    with patch(
        "skeleton.ai.runtime.training.trainer.ReferenceNGramModel.train",
        side_effect=AssertionError("replayed update"),
    ):
        retry = build_governed_artifact(**request)
    assert retry == receipt
    assert request["output_path"].is_file()


def test_second_cli_run_reuses_original_source_and_versions_dataset(tmp_path):
    request = _request(tmp_path)
    first = build_governed_artifact(**request)
    datasets = DatasetRegistry(Path(request["state_directory"]) / "datasets.sqlite3")
    original = datasets.materialized_sources(first["dataset_digest"])[0].envelope
    datasets.close()
    request["run_id"] = "second-operator-run"
    second = build_governed_artifact(**request)
    assert second["dataset_digest"] != first["dataset_digest"]
    datasets = DatasetRegistry(Path(request["state_directory"]) / "datasets.sqlite3")
    assert datasets.dataset(second["dataset_digest"]).version == "2"
    assert datasets.materialized_sources(second["dataset_digest"])[0].envelope == original
    datasets.close()
    assert build_governed_artifact(**request) == second


def test_native_neural_cli_produces_real_loss_and_reloadable_weights(tmp_path):
    pytest.importorskip("numpy")
    request = _request(tmp_path, algorithm="neural")
    request["corpus_paths"][0].write_text("ababab", encoding="utf-8")
    receipt = build_governed_artifact(**request)
    assert receipt["final_loss"] < receipt["initial_loss"]
    assert receipt["update_count"] == 2
    loaded = load_local_model_artifact(request["output_path"])
    assert loaded.model.model_digest == receipt["model_digest"]
    with patch(
        "skeleton.ai.runtime.inference.neural.NumpyRecurrentLM.train_document",
        side_effect=AssertionError("replayed SGD"),
    ):
        assert build_governed_artifact(**request) == receipt


def test_output_publication_failure_retries_completed_checkpoint(tmp_path):
    request = _request(tmp_path)
    with (
        patch(
            "skeleton.ai.runtime.training.cli.write_local_model_artifact", side_effect=OSError("disk failure")
        ),
        pytest.raises(OSError, match="disk failure"),
    ):
        build_governed_artifact(**request)
    runs = TrainingRepository(Path(request["state_directory"]) / "training.sqlite3")
    assert runs.state(request["run_id"]) == "completed"
    runs.close()
    with patch(
        "skeleton.ai.runtime.training.trainer.ReferenceNGramModel.train",
        side_effect=AssertionError("replayed update"),
    ):
        receipt = build_governed_artifact(**request)
    assert receipt["checkpoint_digest"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("rights_refs", ()),
        ("rights_refs", "xyz"),
        ("epochs", True),
        ("learning_rate", float("nan")),
        ("learning_rate", 11.0),
        ("gradient_clip", 1001.0),
        ("algorithm", "cloud"),
        ("classification", "bogus"),
        ("max_steps", -1),
    ],
)
def test_cli_rejects_invalid_admission_before_database_creation(tmp_path, field, value):
    request = _request(tmp_path)
    request[field] = value
    with pytest.raises(GovernedTrainingBuildError):
        build_governed_artifact(**request)
    assert not Path(request["state_directory"]).exists()


@pytest.mark.parametrize(
    "field,value", [("rights_refs", ("license:changed",)), ("seed", 8), ("max_steps", 200_000)]
)
def test_cli_rejects_changed_configuration_under_same_run(tmp_path, field, value):
    request = _request(tmp_path)
    receipt = build_governed_artifact(**request)
    request[field] = value
    with pytest.raises(GovernedTrainingBuildError, match="conflicts"):
        build_governed_artifact(**request)
    assert load_local_model_artifact(request["output_path"]).model.model_digest == receipt["model_digest"]


def test_cli_rejects_changed_actual_bytes_under_same_run(tmp_path):
    request = _request(tmp_path)
    build_governed_artifact(**request)
    request["corpus_paths"][0].write_text("changed actual corpus", encoding="utf-8")
    with pytest.raises(GovernedTrainingBuildError, match="conflicts"):
        build_governed_artifact(**request)


def test_cli_rejects_changed_estimator_code_under_same_run(tmp_path):
    request = _request(tmp_path)
    build_governed_artifact(**request)
    original_read = Path.read_bytes

    def changed_code(path):
        payload = original_read(path)
        if path.parts[-2:] == ("inference", "local.py"):
            return payload + b"\n# changed numerical implementation\n"
        return payload

    with (
        patch.object(Path, "read_bytes", changed_code),
        pytest.raises(GovernedTrainingBuildError, match="conflicts"),
    ):
        build_governed_artifact(**request)


def test_cli_bounds_file_reads_and_rejects_symlink_and_hardlink_inputs(tmp_path):
    request = _request(tmp_path)
    original = request["corpus_paths"][0]
    link = tmp_path / "linked.txt"
    link.symlink_to(original)
    with pytest.raises(GovernedTrainingBuildError, match="symlink"):
        _read_sources((link,), neural=False)
    hardlink = tmp_path / "duplicate.txt"
    hardlink.hardlink_to(original)
    with pytest.raises(GovernedTrainingBuildError, match="duplicate"):
        _read_sources((original, hardlink), neural=False)
    oversized = tmp_path / "oversized.txt"
    oversized.write_bytes(b"x" * 4097)
    with pytest.raises(GovernedTrainingBuildError, match="byte bounds"):
        _read_sources((oversized,), neural=True)


def test_cli_rejects_output_alias_to_corpus(tmp_path):
    request = _request(tmp_path)
    request["output_path"] = request["corpus_paths"][0]
    with pytest.raises(GovernedTrainingBuildError, match="distinct"):
        build_governed_artifact(**request)
    assert request["corpus_paths"][0].read_text() == "two plus two four"


@pytest.mark.parametrize("name", ["datasets.sqlite3-wal", "training.sqlite3-shm", "training.sqlite3-journal"])
def test_cli_output_cannot_overwrite_database_sidecars(tmp_path, name):
    request = _request(tmp_path)
    request["output_path"] = Path(request["state_directory"]) / name
    with pytest.raises(GovernedTrainingBuildError, match="distinct"):
        build_governed_artifact(**request)


def test_cli_rejects_parent_symlink_and_fifo_without_blocking(tmp_path):
    _request(tmp_path)
    linked_directory = tmp_path / "alias"
    linked_directory.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(GovernedTrainingBuildError, match="symlink"):
        _read_sources((linked_directory / "corpus.txt",), neural=False)
    import os

    fifo = tmp_path / "corpus.pipe"
    os.mkfifo(fifo)
    with pytest.raises(GovernedTrainingBuildError, match="regular"):
        _read_sources((fifo,), neural=False)


def test_cli_neural_budget_preflight_does_not_admit_run(tmp_path):
    request = _request(tmp_path, algorithm="neural")
    request["max_steps"] = 2
    with pytest.raises(GovernedTrainingBuildError, match="cumulative execution budget"):
        build_governed_artifact(**request)
    assert not Path(request["state_directory"]).exists()


@pytest.mark.parametrize("dimension", ["max_steps", "max_updates", "max_training_bytes"])
def test_cli_reference_budget_is_effective_before_admission(tmp_path, dimension):
    request = _request(tmp_path)
    request[dimension] = 1
    if dimension == "max_updates":
        second = tmp_path / "second.txt"
        second.write_text("second licensed document")
        request["corpus_paths"] += (second,)
    with pytest.raises(GovernedTrainingBuildError, match="execution budget"):
        build_governed_artifact(**request)
    assert not Path(request["state_directory"]).exists()


def test_invalid_neural_seed_can_be_corrected_without_poisoning_run(tmp_path):
    request = _request(tmp_path, algorithm="neural")
    request["seed"] = -1
    with pytest.raises(GovernedTrainingBuildError, match="non-negative"):
        build_governed_artifact(**request)
    assert not Path(request["state_directory"]).exists()
    request["seed"] = 0
    assert build_governed_artifact(**request)["model_digest"]


@pytest.mark.parametrize("operation", ["revoke", "delete"])
def test_completed_cli_retry_cannot_republish_revoked_or_deleted_sources(tmp_path, operation):
    request = _request(tmp_path)
    receipt = build_governed_artifact(**request)
    datasets = DatasetRegistry(Path(request["state_directory"]) / "datasets.sqlite3")
    digest = datasets.materialized_sources(receipt["dataset_digest"])[0].envelope.content_digest
    if operation == "revoke":
        datasets.revoke_source_rights(
            digest, reason="operator withdraws training consent", command_id="withdraw"
        )
    else:
        datasets.delete_source(digest, reason="operator requests deletion", command_id="withdraw")
    datasets.close()
    request["output_path"].unlink()
    with pytest.raises(PermissionError, match="revoked|deleted|lifecycle|authority|ready|permitted"):
        build_governed_artifact(**request)
    assert not request["output_path"].exists()


def test_revocation_between_training_and_output_prevents_artifact_publication(tmp_path):
    request = _request(tmp_path)
    original = ReferenceLocalTrainer.train

    def train_then_revoke(trainer, *args, **kwargs):
        model, artifact = original(trainer, *args, **kwargs)
        source = trainer.datasets.materialized_sources(artifact.dataset_digest)[0]
        trainer.datasets.revoke_source_rights(
            source.envelope.content_digest,
            reason="consent withdrawn before publication",
            command_id="withdraw-before-output",
        )
        return model, artifact

    with (
        patch.object(ReferenceLocalTrainer, "train", train_then_revoke),
        pytest.raises(PermissionError, match="revoked|permitted|authority"),
    ):
        build_governed_artifact(**request)
    assert not request["output_path"].exists()


def test_cli_main_prints_bounded_receipt_without_corpus(tmp_path, capsys):
    request = _request(tmp_path)
    assert (
        main(
            [
                str(request["corpus_paths"][0]),
                "--state-directory",
                str(request["state_directory"]),
                "--output",
                str(request["output_path"]),
                "--run-id",
                request["run_id"],
                "--dataset-id",
                request["dataset_id"],
                "--rights-ref",
                request["rights_refs"][0],
                "--algorithm",
                "reference",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    receipt = json.loads(output)
    assert receipt["credential_free"]
    assert "two plus two four" not in output

"""Operator state commands exercise real archives and authority failure paths."""

from pathlib import Path
from unittest.mock import patch

import pytest

from skeleton.ai.runtime.training import DatasetRegistry
from skeleton.ai.runtime.training.cli import build_governed_artifact
from skeleton.ai.runtime.training.state_cli import (
    GovernedTrainingStateError,
    archive_training_state,
    inspect_training_state,
    main,
    recover_training_state,
    retain_training_state,
)


def _build(tmp_path, algorithm="reference"):
    source = tmp_path / "owned.txt"
    source.write_text("ababab", encoding="utf-8")
    request = {
        "corpus_paths": (source,),
        "state_directory": tmp_path / "state",
        "output_path": tmp_path / "model.json",
        "run_id": "operator-" + algorithm,
        "dataset_id": "operator-data",
        "rights_refs": ("license:owned",),
        "algorithm": algorithm,
        "hidden_size": 4,
        "epochs": 2,
    }
    return request, build_governed_artifact(**request)


def _archive(tmp_path, request):
    options = {
        "state_directory": request["state_directory"],
        "cas_path": tmp_path / "cas.sqlite3",
        "tenant_id": "owner",
        "trust_context": "owned-training",
    }
    result = archive_training_state(
        **options, run_id=request["run_id"], receipt_output=tmp_path / "backup.json"
    )
    return options, result


@pytest.mark.parametrize("algorithm", ["reference", "neural", "data_parallel"])
def test_operator_commands_restore_actual_cli_after_training_database_loss(tmp_path, algorithm):
    pytest.importorskip("numpy")
    request, original = _build(tmp_path, algorithm)
    options, archived = _archive(tmp_path, request)
    state = Path(request["state_directory"])
    (state / "training.sqlite3").rename(state / "lost-training.sqlite3")
    request["output_path"].unlink()
    restored = recover_training_state(
        **options, dataset_digest=original["dataset_digest"], receipt_path=tmp_path / "backup.json"
    )
    assert restored["state"] == "recovering"
    assert restored["checkpoint_digest"] == archived["checkpoint_digest"] == original["checkpoint_digest"]
    with (
        patch("multiprocessing.process.BaseProcess.start", side_effect=AssertionError("retrained")),
        patch(
            "skeleton.ai.runtime.inference.neural.NumpyRecurrentLM.train_document",
            side_effect=AssertionError("retrained"),
        ),
        patch(
            "skeleton.ai.runtime.inference.local.ReferenceNGramModel.train",
            side_effect=AssertionError("retrained"),
        ),
    ):
        assert build_governed_artifact(**request) == original
    retained = retain_training_state(**options, run_id=request["run_id"], keep_newest=1)
    assert retained["cas_blobs_retained"] is True


def test_operator_archive_cannot_overwrite_database_or_hard_link(tmp_path):
    request, _ = _build(tmp_path)
    database = request["state_directory"] / "datasets.sqlite3"
    alias = tmp_path / "alias.json"
    alias.hardlink_to(database)
    before = database.read_bytes()
    for output in (database, alias, request["state_directory"] / "training.sqlite3-wal"):
        with pytest.raises(GovernedTrainingStateError, match="distinct"):
            archive_training_state(
                state_directory=request["state_directory"],
                run_id=request["run_id"],
                cas_path=tmp_path / "cas.sqlite3",
                receipt_output=output,
                tenant_id="owner",
                trust_context="owned",
            )
    assert database.read_bytes() == before
    assert not (tmp_path / "cas.sqlite3").exists()


def test_operator_recovery_cannot_revive_withdrawn_original_data(tmp_path):
    request, original = _build(tmp_path)
    options, _ = _archive(tmp_path, request)
    datasets = DatasetRegistry(request["state_directory"] / "datasets.sqlite3")
    try:
        datasets.delete_dataset(original["dataset_digest"], reason="withdrawn", command_id="withdraw")
    finally:
        datasets.close()
    (request["state_directory"] / "training.sqlite3").rename(tmp_path / "lost.sqlite3")
    with pytest.raises(PermissionError, match="deleted|withdraw|ready"):
        recover_training_state(
            **options, dataset_digest=original["dataset_digest"], receipt_path=tmp_path / "backup.json"
        )
    assert not (request["state_directory"] / "training.sqlite3").exists()


@pytest.mark.parametrize(
    "receipt",
    [
        '{"run_id":"x","run_id":"y"}',
        '{"version":NaN}',
        "{}",
        "[]",
        "x" * 65537,
    ],
)
def test_operator_recovery_rejects_invalid_receipt_before_creating_training_state(tmp_path, receipt):
    request, original = _build(tmp_path)
    options, _ = _archive(tmp_path, request)
    (tmp_path / "backup.json").write_text(receipt)
    (request["state_directory"] / "training.sqlite3").rename(tmp_path / "lost.sqlite3")
    with pytest.raises((ValueError, RuntimeError)):
        recover_training_state(
            **options, dataset_digest=original["dataset_digest"], receipt_path=tmp_path / "backup.json"
        )
    assert not (request["state_directory"] / "training.sqlite3").exists()


def test_operator_cli_prints_archive_receipt_without_training_text(tmp_path, capsys):
    request, _ = _build(tmp_path)
    assert (
        main(
            [
                "archive",
                "--state-directory",
                str(request["state_directory"]),
                "--run-id",
                request["run_id"],
                "--cas-path",
                str(tmp_path / "cas.sqlite3"),
                "--receipt-output",
                str(tmp_path / "receipt.json"),
                "--tenant-id",
                "owner",
                "--trust-context",
                "owned",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "checkpoint_digest" in output
    assert "ababab" not in output


@pytest.mark.parametrize("algorithm", ["reference", "neural", "data_parallel", "elastic"])
def test_operator_inspection_validates_committed_run_without_exposing_content(tmp_path, algorithm):
    pytest.importorskip("numpy")
    request, built = _build(tmp_path, algorithm)
    report = inspect_training_state(state_directory=request["state_directory"], run_id=request["run_id"])
    assert report["run_id"] == built["run_id"]
    assert report["state"] == "completed"
    assert report["source"]["current_training_admission"] is True
    assert report["checkpoints"][-1]["checkpoint_digest"] == built["checkpoint_digest"]
    assert report["checkpoints"][-1]["semantic_validation"] == "verified_exact_corpus"
    assert report["throughput"]["available"] is False
    assert "ababab" not in str(report)


def test_state_commands_reject_symlink_parent_without_creating_cas(tmp_path):
    request, _ = _build(tmp_path)
    alias = tmp_path / "state-alias"
    alias.symlink_to(request["state_directory"], target_is_directory=True)
    with pytest.raises(GovernedTrainingStateError, match="symlink"):
        archive_training_state(
            state_directory=alias,
            run_id=request["run_id"],
            cas_path=tmp_path / "cas.sqlite3",
            receipt_output=tmp_path / "receipt.json",
            tenant_id="owner",
            trust_context="owned",
        )
    assert not (tmp_path / "cas.sqlite3").exists()


def test_operator_inspection_can_bound_a_large_run_to_latest_evidence(tmp_path):
    request, _ = _build(tmp_path)
    report = inspect_training_state(
        state_directory=request["state_directory"], run_id=request["run_id"], max_points=1
    )
    assert report["window"]["selected_checkpoint_count"] == 1
    assert report["window"]["all_live_checkpoints_selected"] is False
    assert report["checkpoints"][-1]["finished"] is True

"""New governed algorithms compose actual operators, authorities and archives."""

from unittest.mock import patch

import pytest

from skeleton.ai.runtime.inference.artifact import load_local_model_artifact
from skeleton.ai.runtime.training.cli import (
    GovernedTrainingBuildError,
    build_governed_artifact,
)
from skeleton.ai.runtime.training.control import _canonical, _digest
from skeleton.ai.runtime.training.data import DatasetRegistry
from skeleton.ai.runtime.training.state_cli import (
    archive_training_state,
    recover_training_state,
)


def _parent(tmp_path):
    source = tmp_path / "parent.txt"
    source.write_text("ababab", encoding="utf-8")
    request = {
        "corpus_paths": (source,),
        "state_directory": tmp_path / "state",
        "output_path": tmp_path / "parent.json",
        "run_id": "parent",
        "dataset_id": "parent-data",
        "rights_refs": ("license:owned-parent",),
        "algorithm": "neural",
        "hidden_size": 4,
        "epochs": 1,
    }
    return request, build_governed_artifact(**request)


def _preference(tmp_path, *, epochs=2):
    document = _canonical(
        {"schema_version": "skeleton.preference_pair.v1", "prompt": "a", "chosen": "b", "rejected": "c"}
    )
    source = tmp_path / "preference.json"
    source.write_text(document, encoding="utf-8")
    return {
        "corpus_paths": (source,),
        "state_directory": tmp_path / "state",
        "output_path": tmp_path / "preference-model.json",
        "run_id": "preference",
        "dataset_id": "paired-data",
        "rights_refs": ("license:owned-preferences",),
        "algorithm": "preference",
        "parent_run_id": "parent",
        "hidden_size": 4,
        "epochs": epochs,
        "preference_beta": 0.5,
        "evaluation_suite_digest": _digest({"planned_suite": "preference-quality"}),
    }


def test_operator_preference_changes_real_margin_and_retries_without_updates(tmp_path):
    pytest.importorskip("numpy")
    _parent(tmp_path)
    request = _preference(tmp_path)
    result = build_governed_artifact(**request)
    assert result["algorithm"] == "preference"
    assert result["final_margin"] > result["initial_margin"]
    assert result["final_loss"] < result["initial_loss"]
    assert result["update_count"] == request["epochs"]
    assert load_local_model_artifact(request["output_path"]).model.model_digest == result["model_digest"]
    request["output_path"].unlink()
    with patch(
        "skeleton.ai.runtime.training.preference_trainer.preference_objective_and_gradients",
        side_effect=AssertionError("repeated preference update"),
    ):
        assert build_governed_artifact(**request) == result
    changed = {**request, "evaluation_suite_digest": _digest({"changed_suite": "other"})}
    with pytest.raises(GovernedTrainingBuildError, match="conflicts"):
        build_governed_artifact(**changed)


def test_preference_parent_and_candidate_survive_true_database_loss_via_operator_archives(tmp_path):
    pytest.importorskip("numpy")
    parent_request, parent = _parent(tmp_path)
    request = _preference(tmp_path)
    original = build_governed_artifact(**request)
    options = {
        "state_directory": request["state_directory"],
        "cas_path": tmp_path / "cas.sqlite3",
        "tenant_id": "owner",
        "trust_context": "licensed",
    }
    for run in (parent, original):
        archive_training_state(
            **options, run_id=run["run_id"], receipt_output=tmp_path / (run["run_id"] + "-receipt.json")
        )
    (request["state_directory"] / "training.sqlite3").rename(tmp_path / "unavailable-original.sqlite3")
    recover_training_state(
        **options, dataset_digest=parent["dataset_digest"], receipt_path=tmp_path / "parent-receipt.json"
    )
    with patch(
        "skeleton.ai.runtime.inference.neural.NumpyRecurrentLM.train_document",
        side_effect=AssertionError("repeated parent update"),
    ):
        assert build_governed_artifact(**parent_request) == parent
    recover_training_state(
        **options,
        dataset_digest=original["dataset_digest"],
        receipt_path=tmp_path / "preference-receipt.json",
    )
    with patch(
        "skeleton.ai.runtime.training.preference_trainer.preference_objective_and_gradients",
        side_effect=AssertionError("repeated preference update"),
    ):
        assert build_governed_artifact(**request) == original


def test_preference_budget_preflight_does_not_admit_operator_request(tmp_path):
    pytest.importorskip("numpy")
    request = _preference(tmp_path, epochs=128)
    request["max_steps"] = 1
    with pytest.raises(GovernedTrainingBuildError, match="budget"):
        build_governed_artifact(**request)
    assert not request["state_directory"].exists()


def test_parent_withdrawal_between_preference_completion_and_export_blocks_publication(tmp_path):
    pytest.importorskip("numpy")
    from skeleton.ai.runtime.training.preference_trainer import PreferenceLocalTrainer

    _, parent = _parent(tmp_path)
    request = _preference(tmp_path)
    original_train = PreferenceLocalTrainer.train

    def train_then_withdraw(*args, **kwargs):
        result = original_train(*args, **kwargs)
        registry = DatasetRegistry(request["state_directory"] / "datasets.sqlite3")
        try:
            registry.delete_dataset(
                parent["dataset_digest"], reason="parent withdrawn", command_id="withdraw"
            )
        finally:
            registry.close()
        return result

    with patch.object(PreferenceLocalTrainer, "train", train_then_withdraw), pytest.raises(PermissionError):
        build_governed_artifact(**request)
    assert not request["output_path"].exists()


@pytest.mark.parametrize(
    "change",
    [
        {"parent_run_id": None},
        {"evaluation_suite_digest": None},
        {"preference_beta": float("nan")},
        {"epochs": 129},
    ],
)
def test_invalid_preference_admission_cannot_create_state(tmp_path, change):
    request = {**_preference(tmp_path), **change}
    with pytest.raises(GovernedTrainingBuildError):
        build_governed_artifact(**request)
    assert not request["state_directory"].exists()


def test_elastic_completed_operator_retry_preserves_recorded_roster_and_archives(tmp_path):
    pytest.importorskip("numpy")
    source = tmp_path / "elastic.txt"
    source.write_text("abab", encoding="utf-8")
    request = {
        "corpus_paths": (source,),
        "state_directory": tmp_path / "state",
        "output_path": tmp_path / "elastic.json",
        "run_id": "elastic",
        "dataset_id": "elastic-data",
        "rights_refs": ("license:owned",),
        "algorithm": "elastic",
        "world_size": 2,
        "physical_workers": 1,
        "hidden_size": 4,
        "epochs": 2,
    }
    original = build_governed_artifact(**request)
    assert original["physical_workers"] == 1
    request["physical_workers"] = 4
    with patch("multiprocessing.process.BaseProcess.start", side_effect=AssertionError("replayed ranks")):
        assert build_governed_artifact(**request) == original
    options = {
        "state_directory": request["state_directory"],
        "cas_path": tmp_path / "cas.sqlite3",
        "tenant_id": "owner",
        "trust_context": "owned",
    }
    archive_training_state(**options, run_id=request["run_id"], receipt_output=tmp_path / "receipt.json")
    (request["state_directory"] / "training.sqlite3").rename(tmp_path / "lost.sqlite3")
    recover_training_state(
        **options, dataset_digest=original["dataset_digest"], receipt_path=tmp_path / "receipt.json"
    )
    with patch("multiprocessing.process.BaseProcess.start", side_effect=AssertionError("replayed ranks")):
        assert build_governed_artifact(**request) == original


@pytest.mark.parametrize("physical_workers", [True, 0, 5, 1.5])
def test_elastic_rejects_allocation_before_state_creation(tmp_path, physical_workers):
    source = tmp_path / "source.txt"
    source.write_text("ab")
    with pytest.raises(GovernedTrainingBuildError, match="physical_workers"):
        build_governed_artifact(
            corpus_paths=(source,),
            state_directory=tmp_path / "state",
            output_path=tmp_path / "model.json",
            run_id="elastic",
            dataset_id="data",
            rights_refs=("owned",),
            algorithm="elastic",
            physical_workers=physical_workers,
        )
    assert not (tmp_path / "state").exists()

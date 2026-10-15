"""A governed operator run survives loss of its training database via CAS."""

from pathlib import Path
from unittest.mock import patch

import pytest

from skeleton.ai.runtime.inference.artifact import load_local_model_artifact
from skeleton.ai.runtime.training import (
    DatasetRegistry,
    TrainingCheckpointArchive,
    TrainingRepository,
)
from skeleton.ai.runtime.training.cli import build_governed_artifact
from skeleton.storage.cas import GovernedContentStore


@pytest.mark.parametrize("algorithm", ["reference", "neural", "data_parallel"])
def test_governed_operator_restores_archive_into_fresh_database_without_updates(tmp_path, algorithm):
    pytest.importorskip("numpy")
    source = tmp_path / "licensed.txt"
    source.write_text("ababab", encoding="utf-8")
    request = {
        "corpus_paths": (source,),
        "state_directory": tmp_path / "state",
        "output_path": tmp_path / "model.json",
        "run_id": "archive-operator-" + algorithm,
        "dataset_id": "licensed-recovery-data",
        "rights_refs": ("license:operator-owned-recovery",),
        "algorithm": algorithm,
        "hidden_size": 4,
        "epochs": 2,
    }
    original = build_governed_artifact(**request)
    state = Path(request["state_directory"])
    training_path = state / "training.sqlite3"
    datasets = DatasetRegistry(state / "datasets.sqlite3")
    runs = TrainingRepository(training_path)
    store_path = tmp_path / "checkpoint-cas.sqlite3"
    store = GovernedContentStore(str(store_path))
    try:
        corpus = datasets.training_corpus(original["dataset_digest"])
        archive = TrainingCheckpointArchive(runs, store, tenant_id="operator", trust_context="licensed")
        backup = archive.backup(request["run_id"], datasets, corpus)
        assert backup.checkpoint_digest == original["checkpoint_digest"]
    finally:
        store.close()
        runs.close()
        datasets.close()

    # Keep the old database inaccessible and reopen only the independent CAS.
    training_path.rename(state / "inaccessible-original.sqlite3")
    request["output_path"].unlink()
    datasets = DatasetRegistry(state / "datasets.sqlite3")
    destination = TrainingRepository(training_path)
    store = GovernedContentStore(str(store_path))
    try:
        archive = TrainingCheckpointArchive(
            destination, store, tenant_id="operator", trust_context="licensed"
        )
        contents = archive.verify_backup(backup, datasets, corpus)
        destination.register_run(contents.manifest, datasets)
        destination.bind_execution(request["run_id"], contents.binding)
        checkpoint = archive.restore(backup, datasets, corpus)
        assert checkpoint.digest == original["checkpoint_digest"]
    finally:
        store.close()
        destination.close()
        datasets.close()

    update = (
        "skeleton.ai.runtime.training.trainer.ReferenceNGramModel.train"
        if algorithm == "reference"
        else "skeleton.ai.runtime.inference.neural.NumpyRecurrentLM.train_document"
    )
    with (
        patch(update, side_effect=AssertionError("archive recovery repeated learned updates")),
        patch(
            "multiprocessing.process.BaseProcess.start", side_effect=AssertionError("recovery spawned ranks")
        ),
    ):
        recovered = build_governed_artifact(**request)
    assert recovered == original
    assert load_local_model_artifact(request["output_path"]).model.model_digest == original["model_digest"]

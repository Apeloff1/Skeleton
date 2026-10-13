from __future__ import annotations

import json
import multiprocessing
import os
import signal
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from skeleton.ai.runtime.training import (
    DatasetRegistry,
    IngestEnvelope,
    TrainingRepository,
    TrainingRunManifest,
    TrainingStateError,
)
from skeleton.ai.runtime.training import elastic_trainer as elastic
from skeleton.ai.runtime.training.control import _digest
from skeleton.ai.runtime.training.data import MaterializedTrainingSource
from skeleton.ai.runtime.training.distributed_trainer import (
    _PARAMETERS,
    LocalDataParallelTrainer,
)
from skeleton.ai.runtime.training.elastic_trainer import ElasticLocalTrainer

NOW = datetime(2026, 10, 4, 18, tzinfo=UTC)
CORPUS = ("aba", "abc", "café", "abb", "ab")
KWARGS = {"hidden_size": 4, "epochs": 2, "learning_rate": 0.2, "gradient_clip": 1.0, "now": NOW}


class AbruptStop(BaseException):
    pass


def _fixture(path, *, logical_ranks=4, budget=None, timeout=20):
    path.mkdir(parents=True, exist_ok=True)
    datasets = DatasetRegistry(path / "datasets.sqlite3")
    raw = json.dumps(list(CORPUS), ensure_ascii=False).encode()
    envelope = IngestEnvelope.from_bytes(
        source_id="fixture://elastic-corpus",
        payload=raw,
        parser_version="json-documents@1",
        classification="internal",
        rights=("training", "evaluation"),
        trusted=True,
        acquired_at=NOW,
    )
    source = MaterializedTrainingSource(
        envelope=envelope, payload=raw, format="json_documents", rights_refs=("license:elastic-fixture",)
    )
    receipt = datasets.ingest_materialized(
        ingestion_id="elastic-ingestion",
        dataset_id="elastic-corpus",
        expected_version=0,
        sources={"train": (source,)},
        classification="internal",
        permitted_uses=("training", "evaluation"),
        retention_class="test",
    )
    runs = TrainingRepository(path / "training.sqlite3")
    initial = ElasticLocalTrainer.initialize_model("elastic-run", hidden_size=4, seed=7)
    manifest = TrainingRunManifest(
        run_id="elastic-run",
        dataset_digest=receipt.dataset_digest,
        base_model_digest=initial.model_digest,
        code_digest=_digest("logical-mean-sgd@1"),
        environment_digest=_digest("elastic-fixture-runtime"),
        hyperparameters={
            "algorithm": "elastic",
            "hidden_size": 4,
            "epochs": 2,
            "learning_rate": 0.2,
            "gradient_clip": 1.0,
        },
        seed=7,
        world_size=logical_ranks,
        parallelism="data_parallel",
        collective_timeout_seconds=timeout,
        resource_budget=budget
        or {
            "max_steps": 100,
            "max_updates": 20,
            "max_training_bytes": 200,
            "max_barriers": 10,
            "max_processes": 4,
        },
    )
    return datasets, runs, manifest, envelope.content_digest


def _no_workers():
    assert not [
        child
        for child in multiprocessing.active_children()
        if child.name.startswith("skeleton-training-rank-")
    ]


def _reopen(path, datasets, runs):
    datasets.close()
    runs.close()
    return DatasetRegistry(path / "datasets.sqlite3"), TrainingRepository(path / "training.sqlite3")


def _interrupt_after(trainer, monkeypatch, count, calls):
    original = trainer._barrier

    def interrupted(pool, binding, lease, model, cursor, documents):
        if cursor["barrier_count"] == count:
            raise AbruptStop()
        calls.append(cursor["barrier_count"] + 1)
        return original(pool, binding, lease, model, cursor, documents)

    monkeypatch.setattr(trainer, "_barrier", interrupted)


@pytest.mark.parametrize("logical_ranks,physical_workers", [(2, 1), (2, 4), (3, 2), (4, 1), (4, 3), (4, 4)])
def test_actual_physical_placement_matches_fixed_logical_algorithm(tmp_path, logical_ranks, physical_workers):
    datasets, runs, manifest, _ = _fixture(tmp_path / "elastic", logical_ranks=logical_ranks)
    model, artifact = ElasticLocalTrainer(datasets, runs).train(
        manifest, CORPUS, physical_workers=physical_workers, **KWARGS
    )
    fixed_data, fixed_runs, fixed_manifest, _ = _fixture(tmp_path / "fixed", logical_ranks=logical_ranks)
    fixed_manifest = replace(
        fixed_manifest,
        hyperparameters={
            key: value for key, value in fixed_manifest.hyperparameters.items() if key != "algorithm"
        },
    )
    fixed, fixed_artifact = LocalDataParallelTrainer(fixed_data, fixed_runs).train(
        fixed_manifest, CORPUS, **KWARGS
    )
    assert model.model_digest == fixed.model_digest
    for name in _PARAMETERS:
        assert np.array_equal(getattr(model, name), getattr(fixed, name))
    assert artifact.initial_loss == fixed_artifact.initial_loss
    assert artifact.final_loss == fixed_artifact.final_loss < artifact.initial_loss
    assert artifact.physical_workers == physical_workers
    assert artifact.world_size == logical_ranks
    assert artifact.membership_change_count == 0
    for checkpoint in runs.checkpoints(manifest.run_id):
        barrier = runs.checkpoint_payload(checkpoint)["barrier"]
        if barrier is None:
            continue
        membership = barrier["membership"]
        assert len(membership["worker_pids"]) == physical_workers
        assert len(set(membership["worker_pids"])) == physical_workers
        assert os.getpid() not in membership["worker_pids"]
        assert membership["rank_to_worker"] == [rank % physical_workers for rank in range(logical_ranks)]
        assert [rank["worker_pid"] for rank in barrier["ranks"]] == [
            membership["worker_pids"][slot] for slot in membership["rank_to_worker"]
        ]
    _no_workers()


def test_reopened_scale_down_then_scale_up_skips_committed_logical_updates(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(tmp_path / "resized")
    trainer = ElasticLocalTrainer(datasets, runs)
    calls = []
    _interrupt_after(trainer, monkeypatch, 1, calls)
    with pytest.raises(AbruptStop):
        trainer.train(manifest, CORPUS, physical_workers=2, **KWARGS)
    first = runs.latest_checkpoint(manifest.run_id)
    datasets, runs = _reopen(tmp_path / "resized", datasets, runs)
    trainer = ElasticLocalTrainer(datasets, runs)
    _interrupt_after(trainer, monkeypatch, 2, calls)
    with pytest.raises(AbruptStop):
        trainer.train(manifest, CORPUS, physical_workers=1, **KWARGS)
    second = runs.latest_checkpoint(manifest.run_id)
    datasets, runs = _reopen(tmp_path / "resized", datasets, runs)
    trainer = ElasticLocalTrainer(datasets, runs)
    original = trainer._barrier

    def observe(pool, binding, lease, model, cursor, documents):
        calls.append(cursor["barrier_count"] + 1)
        return original(pool, binding, lease, model, cursor, documents)

    monkeypatch.setattr(trainer, "_barrier", observe)
    resumed, artifact = trainer.train(manifest, CORPUS, physical_workers=4, **KWARGS)
    assert calls == [1, 2, 3, 4]
    assert [
        runs.checkpoint_payload(cp)["barrier"]["membership"]["physical_workers"]
        for cp in reversed(runs.checkpoints(manifest.run_id))
        if cp.step
    ] == [2, 1, 4, 4]
    assert artifact.membership_change_count == 2
    assert artifact.physical_workers == 4
    assert artifact.update_count == 10
    assert artifact.token_count == 2 * sum(len(document.encode()) + 1 for document in CORPUS)
    assert runs.latest_checkpoint(manifest.run_id).worker_epoch == 2
    assert first.worker_epoch == 0 and second.worker_epoch == 1
    checkpoints = list(reversed(runs.checkpoints(manifest.run_id)))
    previous = None
    consumed = []
    for cp in checkpoints[1:]:
        barrier = runs.checkpoint_payload(cp)["barrier"]
        membership = barrier["membership"]
        assert membership["previous_membership_digest"] == (None if previous is None else _digest(previous))
        consumed.extend(
            (barrier["source_epoch"], rank["document_index"])
            for rank in barrier["ranks"]
            if rank["status"] == "updated"
        )
        previous = membership
    assert consumed == [(epoch, index) for epoch in range(2) for index in range(len(CORPUS))]
    uninterrupted_data, uninterrupted_runs, uninterrupted_manifest, _ = _fixture(tmp_path / "uninterrupted")
    uninterrupted, uninterrupted_artifact = ElasticLocalTrainer(uninterrupted_data, uninterrupted_runs).train(
        uninterrupted_manifest, CORPUS, physical_workers=3, **KWARGS
    )
    assert resumed.model_digest == uninterrupted.model_digest
    assert artifact.final_loss == uninterrupted_artifact.final_loss
    for name in _PARAMETERS:
        assert np.array_equal(getattr(resumed, name), getattr(uninterrupted, name))
    _no_workers()


def test_actual_physical_process_death_rolls_back_and_resizes_recovery(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    trainer = ElasticLocalTrainer(datasets, runs)
    original = trainer._barrier
    prior = []

    def kill(pool, binding, lease, model, cursor, documents):
        if cursor["barrier_count"] == 1:
            prior.append(runs.latest_checkpoint(manifest.run_id).digest)
            pool.processes[1].kill()
            pool.processes[1].join(timeout=1)
        return original(pool, binding, lease, model, cursor, documents)

    monkeypatch.setattr(trainer, "_barrier", kill)
    with pytest.raises(TrainingStateError, match="rank .* failed"):
        trainer.train(manifest, CORPUS, physical_workers=2, **KWARGS)
    assert runs.latest_checkpoint(manifest.run_id).digest == prior[0]
    assert runs.state(manifest.run_id) == "failed"
    _no_workers()
    datasets, runs = _reopen(tmp_path, datasets, runs)
    model, artifact = ElasticLocalTrainer(datasets, runs).train(
        manifest, CORPUS, physical_workers=1, **KWARGS
    )
    assert artifact.membership_change_count == 1 and artifact.update_count == 10
    assert len(runs.checkpoints(manifest.run_id)) == 5
    assert model.model_digest == runs.latest_checkpoint(manifest.run_id).model_digest
    _no_workers()


@pytest.mark.skipif(not hasattr(signal, "SIGSTOP"), reason="POSIX worker stop drill")
def test_stopped_process_times_out_and_is_killed_before_return(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    trainer = ElasticLocalTrainer(datasets, runs)
    original = trainer._barrier

    def stop(pool, binding, lease, model, cursor, documents):
        pool.timeout = 0.2
        os.kill(pool.processes[0].pid, signal.SIGSTOP)
        return original(pool, binding, lease, model, cursor, documents)

    monkeypatch.setattr(trainer, "_barrier", stop)
    with pytest.raises(TrainingStateError, match="timed out"):
        trainer.train(manifest, CORPUS, physical_workers=1, **KWARGS)
    assert runs.latest_checkpoint(manifest.run_id).step == 0
    assert len(runs.checkpoints(manifest.run_id)) == 1
    _no_workers()


@pytest.mark.parametrize("physical_workers", [0, 5, True, 1.5])
def test_invalid_current_membership_denied_before_owner_or_process_creation(
    tmp_path, monkeypatch, physical_workers
):
    datasets, runs, manifest, _ = _fixture(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("allocation must not occur")

    monkeypatch.setattr(elastic._ElasticPool, "__enter__", forbidden)
    with pytest.raises(TrainingStateError, match="physical_workers"):
        ElasticLocalTrainer(datasets, runs).train(
            manifest, CORPUS, physical_workers=physical_workers, **KWARGS
        )
    assert runs._db.execute("SELECT count(*) FROM training_run").fetchone()[0] == 0


def test_physical_budget_bounds_real_processes_independently_of_logical_ranks(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(
        tmp_path, budget={"max_processes": 1, "max_barriers": 4, "max_steps": 100}
    )
    trainer = ElasticLocalTrainer(datasets, runs)
    with pytest.raises(TrainingStateError, match="max_processes"):
        trainer.train(manifest, CORPUS, physical_workers=2, **KWARGS)
    model, artifact = trainer.train(manifest, CORPUS, physical_workers=1, **KWARGS)
    assert artifact.world_size == 4 and artifact.physical_workers == 1
    assert model.model_digest == artifact.model_digest
    _no_workers()


@pytest.mark.parametrize(
    "budget", [{"max_barriers": 3}, {"max_updates": 9}, {"max_steps": 35}, {"max_training_bytes": 25}]
)
def test_cumulative_budget_denied_before_any_process_or_checkpoint(tmp_path, monkeypatch, budget):
    datasets, runs, manifest, _ = _fixture(tmp_path, budget={"max_processes": 4, **budget})

    def forbidden(*args, **kwargs):
        raise AssertionError("allocation must not occur")

    monkeypatch.setattr(elastic._ElasticPool, "__enter__", forbidden)
    with pytest.raises(TrainingStateError, match="budget"):
        ElasticLocalTrainer(datasets, runs).train(manifest, CORPUS, physical_workers=1, **KWARGS)
    assert runs._db.execute("SELECT count(*) FROM training_run").fetchone()[0] == 0


def test_completed_retry_different_process_count_returns_recorded_membership_without_allocation(
    tmp_path, monkeypatch
):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    model, artifact = ElasticLocalTrainer(datasets, runs).train(
        manifest, CORPUS, physical_workers=1, **KWARGS
    )
    datasets, runs = _reopen(tmp_path, datasets, runs)
    trainer = ElasticLocalTrainer(datasets, runs)

    def forbidden(*args, **kwargs):
        raise AssertionError("completed reload must not allocate processes")

    monkeypatch.setattr(elastic._ElasticPool, "__enter__", forbidden)
    loaded, reloaded = trainer.load_artifact(manifest.run_id)
    retry, retried = trainer.train(manifest, CORPUS, physical_workers=4, **KWARGS)
    assert loaded.model_digest == retry.model_digest == model.model_digest
    assert artifact == reloaded == retried
    assert retried.physical_workers == 1
    assert len(runs.checkpoints(manifest.run_id)) == 5


def test_stale_parent_epoch_cannot_commit_actual_computed_logical_updates(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    trainer = ElasticLocalTrainer(datasets, runs)
    original = trainer._barrier

    def stale(pool, binding, lease, model, cursor, documents):
        updated = original(pool, binding, lease, model, cursor, documents)
        runs.recover(manifest.run_id)
        return updated

    monkeypatch.setattr(trainer, "_barrier", stale)
    with pytest.raises(TrainingStateError, match="stale|current|state|running"):
        trainer.train(manifest, CORPUS, physical_workers=1, **KWARGS)
    assert runs.latest_checkpoint(manifest.run_id).step == 0
    assert len(runs.checkpoints(manifest.run_id)) == 1
    _no_workers()


def test_revocation_after_actual_updates_prevents_full_barrier_commit_and_retry(tmp_path, monkeypatch):
    datasets, runs, manifest, source_digest = _fixture(tmp_path)
    trainer = ElasticLocalTrainer(datasets, runs)
    original = trainer._barrier

    def revoke(pool, binding, lease, model, cursor, documents):
        result = original(pool, binding, lease, model, cursor, documents)
        datasets.revoke_source_rights(
            source_digest, reason="withdraw training rights", command_id="revoke-elastic"
        )
        return result

    monkeypatch.setattr(trainer, "_barrier", revoke)
    with pytest.raises(PermissionError, match="revok|authority|rights"):
        trainer.train(manifest, CORPUS, physical_workers=1, **KWARGS)
    assert runs.latest_checkpoint(manifest.run_id).step == 0
    with pytest.raises(PermissionError, match="revok|authority|rights"):
        ElasticLocalTrainer(datasets, runs).train(manifest, CORPUS, physical_workers=2, **KWARGS)
    _no_workers()


@pytest.mark.parametrize(
    "mutation",
    [
        "mapping",
        "duplicate_pid",
        "float_count",
        "stale_epoch",
        "consumed_position",
        "resize_without_fence",
        "stale_logical_receipt",
        "float_rank",
    ],
)
def test_malformed_membership_or_rank_response_rolls_back(tmp_path, monkeypatch, mutation):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    trainer = ElasticLocalTrainer(datasets, runs)
    original = trainer._barrier_metadata

    def malformed(pool, binding, lease, cursor, barrier):
        result = original(pool, binding, lease, cursor, barrier)
        membership = result["membership"]
        if mutation == "mapping":
            membership["rank_to_worker"][0] = 1
        elif mutation == "duplicate_pid":
            membership["worker_pids"][1] = membership["worker_pids"][0]
        elif mutation == "float_count":
            membership["physical_workers"] = 2.0
        elif mutation == "stale_epoch":
            membership["worker_epoch"] -= 1
        elif mutation == "consumed_position":
            membership["consumed_documents_before"] += 1
        elif mutation == "resize_without_fence":
            if cursor["barrier_count"] == 0:
                return result
            membership["previous_physical_workers"] = 1
            membership["previous_worker_pids"] = membership["worker_pids"][:1]
            membership["resize_count"] = 1
        elif mutation == "stale_logical_receipt":
            result["ranks"][0]["worker_epoch"] -= 1
        elif mutation == "float_rank":
            result["ranks"][0]["rank"] = 0.0
        return result

    monkeypatch.setattr(trainer, "_barrier_metadata", malformed)
    with pytest.raises(TrainingStateError, match="receipt"):
        trainer.train(manifest, CORPUS, physical_workers=2, **KWARGS)
    expected = 1 if mutation == "resize_without_fence" else 0
    assert (
        runs.checkpoint_payload(runs.latest_checkpoint(manifest.run_id))["cursor"]["barrier_count"]
        == expected
    )
    _no_workers()


def test_payload_corruption_and_conflicting_immutable_retry_fail_before_allocation(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    trainer = ElasticLocalTrainer(datasets, runs)
    _interrupt_after(trainer, monkeypatch, 1, [])
    with pytest.raises(AbruptStop):
        trainer.train(manifest, CORPUS, physical_workers=2, **KWARGS)

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid input must not allocate")

    monkeypatch.setattr(elastic._ElasticPool, "__enter__", forbidden)
    with pytest.raises(TrainingStateError, match="conflict"):
        ElasticLocalTrainer(datasets, runs).train(
            manifest, CORPUS, physical_workers=1, **{**KWARGS, "epochs": 3}
        )
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    runs._db.execute(
        "UPDATE training_checkpoint_payload SET payload_json=? WHERE checkpoint_digest=?",
        ("{}", checkpoint.digest),
    )
    runs._db.commit()
    with pytest.raises(TrainingStateError, match="payload"):
        ElasticLocalTrainer(datasets, runs).train(manifest, CORPUS, physical_workers=1, **KWARGS)


def test_contract_matches_exact_implementation_payload_and_execution_only_configuration(tmp_path):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    _, artifact = ElasticLocalTrainer(datasets, runs).train(manifest, CORPUS, physical_workers=1, **KWARGS)
    root = Path(__file__).resolve().parents[2]
    contract = json.loads((root / "machine/ai_local_elastic_training.json").read_text())
    binding = runs.execution_binding(manifest.run_id)
    payload = runs.checkpoint_payload(runs.latest_checkpoint(manifest.run_id))
    assert set(contract["binding"]["fields"]) == set(binding)
    assert set(contract["binding"]["training_config_fields"]) == set(binding["training_config"])
    assert set(contract["resume_payload"]["fields"]) == set(payload)
    assert set(contract["resume_payload"]["membership_fields"]) == set(payload["barrier"]["membership"])
    assert binding["schema_version"] == contract["binding"]["schema_version"]
    assert payload["schema_version"] == contract["resume_payload"]["schema_version"]
    assert "physical_workers" not in binding["training_config"]
    assert binding["training_config"]["max_physical_workers"] == 4
    assert artifact.membership_receipt_digest == _digest(payload["barrier"]["membership"])
    assert not contract["remote_cluster_training_supported"]
    assert not contract["masterplan_completion_authorized"]


def test_cas_reimport_restarts_with_new_physical_membership_and_preserves_weights(tmp_path, monkeypatch):
    from skeleton.ai.runtime.training.checkpoint_archive import (
        TrainingCheckpointArchive,
    )
    from skeleton.storage.cas import GovernedContentStore

    datasets, runs, manifest, _ = _fixture(tmp_path)
    trainer = ElasticLocalTrainer(datasets, runs)
    _interrupt_after(trainer, monkeypatch, 1, [])
    with pytest.raises(AbruptStop):
        trainer.train(manifest, CORPUS, physical_workers=2, **KWARGS)
    store = GovernedContentStore(tmp_path / "cas.sqlite3")
    archive = TrainingCheckpointArchive(
        runs, store, tenant_id="elastic-fixture", trust_context="training-internal"
    )
    receipt = archive.backup(manifest.run_id, datasets, CORPUS)
    binding = runs.execution_binding(manifest.run_id)
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    target = TrainingRepository(tmp_path / "restored.sqlite3")
    target.register_run(manifest, datasets, created_at=NOW)
    target.bind_execution(manifest.run_id, binding)
    target.close()
    store.close()
    store = GovernedContentStore(tmp_path / "cas.sqlite3")
    target = TrainingRepository(tmp_path / "restored.sqlite3")
    importing = TrainingCheckpointArchive(
        target, store, tenant_id="elastic-fixture", trust_context="training-internal"
    )
    assert importing.restore(receipt, datasets, CORPUS) == checkpoint
    restored, artifact = ElasticLocalTrainer(datasets, target).train(
        manifest, CORPUS, physical_workers=1, **KWARGS
    )
    baseline = TrainingRepository(tmp_path / "baseline.sqlite3")
    expected, expected_artifact = ElasticLocalTrainer(datasets, baseline).train(
        manifest, CORPUS, physical_workers=3, **KWARGS
    )
    assert restored.model_digest == expected.model_digest
    assert artifact.final_loss == expected_artifact.final_loss
    assert artifact.membership_change_count == 1
    assert artifact.physical_workers == 1
    assert len(target.checkpoints(manifest.run_id)) == 4
    _no_workers()


def test_finished_checkpoint_retry_changes_no_recorded_membership(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    original_complete = runs.complete

    def interrupt(*args, **kwargs):
        raise AbruptStop()

    monkeypatch.setattr(runs, "complete", interrupt)
    with pytest.raises(AbruptStop):
        ElasticLocalTrainer(datasets, runs).train(manifest, CORPUS, physical_workers=1, **KWARGS)
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    assert runs.checkpoint_payload(checkpoint)["finished"] is True
    monkeypatch.setattr(runs, "complete", original_complete)

    def forbidden(*args, **kwargs):
        raise AssertionError("finished barrier must not allocate twice")

    monkeypatch.setattr(elastic._ElasticPool, "__enter__", forbidden)
    model, artifact = ElasticLocalTrainer(datasets, runs).train(
        manifest, CORPUS, physical_workers=4, **KWARGS
    )
    assert artifact.physical_workers == 1
    assert artifact.membership_change_count == 0
    assert artifact.checkpoint_digest == checkpoint.digest
    assert model.model_digest == checkpoint.model_digest
    assert len(runs.checkpoints(manifest.run_id)) == 5
    _no_workers()


def test_empty_startup_failure_recovers_before_initial_checkpoint_at_new_membership(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    original_start = runs.start

    def interrupted_start(run_id):
        original_start(run_id)
        raise AbruptStop()

    monkeypatch.setattr(runs, "start", interrupted_start)
    with pytest.raises(AbruptStop):
        ElasticLocalTrainer(datasets, runs).train(manifest, CORPUS, physical_workers=2, **KWARGS)
    assert runs.state(manifest.run_id) == "running"
    assert runs.latest_checkpoint(manifest.run_id) is None
    monkeypatch.setattr(runs, "start", original_start)
    _, artifact = ElasticLocalTrainer(datasets, runs).train(manifest, CORPUS, physical_workers=1, **KWARGS)
    assert runs.latest_checkpoint(manifest.run_id).worker_epoch == 1
    assert artifact.physical_workers == 1
    assert artifact.membership_change_count == 0
    _no_workers()


@pytest.mark.parametrize("conflict", ["logical_ranks", "budget", "timeout", "learning_rate", "corpus"])
def test_conflicting_elastic_retry_never_allocates_replacement_processes(tmp_path, monkeypatch, conflict):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    trainer = ElasticLocalTrainer(datasets, runs)
    _interrupt_after(trainer, monkeypatch, 1, [])
    with pytest.raises(AbruptStop):
        trainer.train(manifest, CORPUS, physical_workers=2, **KWARGS)
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    arguments = dict(KWARGS)
    corpus = CORPUS
    if conflict == "logical_ranks":
        manifest = replace(manifest, world_size=2)
    elif conflict == "budget":
        manifest = replace(manifest, resource_budget={**manifest.resource_budget, "max_processes": 3})
    elif conflict == "timeout":
        manifest = replace(manifest, collective_timeout_seconds=10)
    elif conflict == "learning_rate":
        arguments["learning_rate"] = 0.3
    elif conflict == "corpus":
        corpus = (*CORPUS[:-1], "changed")

    def forbidden(*args, **kwargs):
        raise AssertionError("conflicting retry must not create replacement processes")

    monkeypatch.setattr(elastic._ElasticPool, "__enter__", forbidden)
    with pytest.raises((TrainingStateError, ValueError)):
        ElasticLocalTrainer(datasets, runs).train(manifest, corpus, physical_workers=1, **arguments)
    assert runs.latest_checkpoint(manifest.run_id) == checkpoint
    assert len(runs.checkpoints(manifest.run_id)) == 2

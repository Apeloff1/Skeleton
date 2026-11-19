from __future__ import annotations

import json
import math
import multiprocessing
import os
import signal
import threading
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from skeleton.ai.runtime.inference.neural import NumpyRecurrentLM
from skeleton.ai.runtime.training import (
    DatasetRegistry,
    IngestEnvelope,
    TrainingRepository,
    TrainingRunManifest,
    TrainingStateError,
)
from skeleton.ai.runtime.training import distributed_trainer as parallel
from skeleton.ai.runtime.training.control import _digest
from skeleton.ai.runtime.training.data import MaterializedTrainingSource
from skeleton.ai.runtime.training.distributed_trainer import LocalDataParallelTrainer

NOW = datetime(2026, 10, 4, 18, tzinfo=UTC)
CORPUS = ("aba", "abc", "café", "abb", "ab")
KWARGS = {"hidden_size": 4, "epochs": 2, "learning_rate": 0.2, "gradient_clip": 1.0, "now": NOW}
PARAMETERS = ("embedding", "recurrent", "hidden_bias", "output", "output_bias")


class AbruptStop(BaseException):
    pass


def _fixture(tmp_path, *, corpus=CORPUS, world_size=2, budget=None, timeout=20):
    tmp_path.mkdir(parents=True, exist_ok=True)
    datasets = DatasetRegistry(tmp_path / "datasets.sqlite3")
    raw = json.dumps(list(corpus), ensure_ascii=False).encode()
    envelope = IngestEnvelope.from_bytes(
        source_id="fixture://observed-parallel-corpus",
        payload=raw,
        parser_version="json-documents@1",
        classification="internal",
        rights=("training", "evaluation"),
        trusted=True,
        acquired_at=NOW,
    )
    source = MaterializedTrainingSource(
        envelope=envelope, payload=raw, format="json_documents", rights_refs=("license:parallel-fixture",)
    )
    receipt = datasets.ingest_materialized(
        ingestion_id="parallel-ingestion",
        dataset_id="parallel-corpus",
        expected_version=0,
        sources={"train": (source,)},
        classification="internal",
        permitted_uses=("training", "evaluation"),
        retention_class="test",
    )
    runs = TrainingRepository(tmp_path / "training.sqlite3")
    initial = LocalDataParallelTrainer.initialize_model("parallel-run", hidden_size=4, seed=7)
    manifest = TrainingRunManifest(
        run_id="parallel-run",
        dataset_digest=receipt.dataset_digest,
        base_model_digest=initial.model_digest,
        code_digest=_digest("local-synchronous-mean-sgd@1"),
        environment_digest=_digest("parallel-fixture-runtime"),
        hyperparameters={"hidden_size": 4, "epochs": 2, "learning_rate": 0.2, "gradient_clip": 1.0},
        seed=7,
        world_size=world_size,
        parallelism="data_parallel",
        collective_timeout_seconds=timeout,
        resource_budget=budget
        or {
            "max_steps": 100,
            "max_updates": 20,
            "max_training_bytes": 200,
            "max_barriers": 10,
            "max_processes": world_size,
        },
    )
    return datasets, runs, manifest, envelope.content_digest


def _serial_mean(manifest, corpus=CORPUS):
    model = LocalDataParallelTrainer.initialize_model(manifest.run_id, hidden_size=4, seed=manifest.seed)
    for _ in range(KWARGS["epochs"]):
        for start in range(0, len(corpus), manifest.world_size):
            snapshot = model.to_dict()
            ranks = []
            for document in corpus[start : start + manifest.world_size]:
                rank = NumpyRecurrentLM.from_dict(snapshot)
                rank.train_document(
                    document, learning_rate=KWARGS["learning_rate"], gradient_clip=KWARGS["gradient_clip"]
                )
                ranks.append(rank)
            parameters = {}
            for name in PARAMETERS:
                total = np.zeros_like(getattr(model, name))
                for rank in ranks:
                    total += getattr(rank, name)
                parameters[name] = total / len(ranks)
            model = NumpyRecurrentLM(model_id=model.model_id, config=model.config, parameters=parameters)
    return model


def _assert_no_ranks():
    assert not [
        process
        for process in multiprocessing.active_children()
        if process.name.startswith("skeleton-training-rank-")
    ]


@pytest.mark.parametrize("world_size", [2, 3, 4])
def test_spawned_ranks_match_ordered_synchronous_mean_and_commit_complete_barriers(tmp_path, world_size):
    datasets, runs, manifest, _ = _fixture(tmp_path, world_size=world_size)
    model, artifact = LocalDataParallelTrainer(datasets, runs).train(manifest, CORPUS, **KWARGS)
    expected = _serial_mean(manifest)
    assert model.model_digest == expected.model_digest
    for name in PARAMETERS:
        assert np.array_equal(getattr(model, name), getattr(expected, name))
    assert artifact.final_loss < artifact.initial_loss
    assert artifact.world_size == world_size
    assert artifact.strategy == "local_spawned_processes"
    assert artifact.barrier_count == 2 * math.ceil(len(CORPUS) / world_size)
    assert artifact.update_count == 2 * len(CORPUS)
    assert artifact.token_count == 2 * sum(len(document.encode()) + 1 for document in CORPUS)
    checkpoints = tuple(reversed(runs.checkpoints(manifest.run_id)))
    assert len(checkpoints) == artifact.barrier_count + 1
    previous = checkpoints[0]
    pids = None
    for checkpoint in checkpoints[1:]:
        payload = runs.checkpoint_payload(checkpoint)
        barrier = payload["barrier"]
        assert barrier["input_model_digest"] == previous.model_digest
        assert barrier["output_model_digest"] == checkpoint.model_digest
        assert [receipt["rank"] for receipt in barrier["ranks"]] == list(range(world_size))
        actual_pids = tuple(receipt["worker_pid"] for receipt in barrier["ranks"])
        assert len(set(actual_pids)) == world_size
        assert os.getpid() not in actual_pids
        if pids is None:
            pids = actual_pids
        assert actual_pids == pids
        assert sum(receipt["targets"] for receipt in barrier["ranks"]) == checkpoint.step - previous.step
        if barrier["source_document_index"] + world_size > len(CORPUS):
            assert any(receipt["status"] == "idle" for receipt in barrier["ranks"])
        previous = checkpoint
    assert artifact.barrier_receipt_digest == _digest(runs.checkpoint_payload(checkpoints[-1])["barrier"])
    _assert_no_ranks()


def test_reopen_resume_skips_committed_barriers_and_matches_uninterrupted_weights(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    trainer = LocalDataParallelTrainer(datasets, runs)
    original = trainer._barrier
    completed = []

    def interrupt(pool, binding, lease, model, cursor, documents):
        if cursor["barrier_count"] == 2:
            raise AbruptStop()
        completed.append(cursor["barrier_count"] + 1)
        return original(pool, binding, lease, model, cursor, documents)

    monkeypatch.setattr(trainer, "_barrier", interrupt)
    with pytest.raises(AbruptStop):
        trainer.train(manifest, CORPUS, **KWARGS)
    assert completed == [1, 2]
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    assert runs.checkpoint_payload(checkpoint)["cursor"]["document_index"] == 4
    assert runs.state(manifest.run_id) == "running"
    datasets.close()
    runs.close()
    _assert_no_ranks()
    datasets = DatasetRegistry(tmp_path / "datasets.sqlite3")
    runs = TrainingRepository(tmp_path / "training.sqlite3")
    trainer = LocalDataParallelTrainer(datasets, runs)
    original = trainer._barrier
    resumed = []

    def observe(pool, binding, lease, model, cursor, documents):
        resumed.append(cursor["barrier_count"] + 1)
        return original(pool, binding, lease, model, cursor, documents)

    monkeypatch.setattr(trainer, "_barrier", observe)
    model, artifact = trainer.train(manifest, CORPUS, **KWARGS)
    assert resumed == [3, 4, 5, 6]
    uninterrupted_data, uninterrupted_runs, uninterrupted_manifest, _ = _fixture(tmp_path / "uninterrupted")
    uninterrupted, _ = LocalDataParallelTrainer(uninterrupted_data, uninterrupted_runs).train(
        uninterrupted_manifest, CORPUS, **KWARGS
    )
    assert model.model_digest == uninterrupted.model_digest
    assert artifact.update_count == 10
    assert len(runs.checkpoints(manifest.run_id)) == 7
    assert runs.latest_checkpoint(manifest.run_id).worker_epoch == 1
    _assert_no_ranks()


def test_actual_rank_exit_keeps_prior_checkpoint_and_recovery_replays_only_failed_barrier(
    tmp_path, monkeypatch
):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    trainer = LocalDataParallelTrainer(datasets, runs)
    original = trainer._barrier
    prior = []

    def kill_rank(pool, binding, lease, model, cursor, documents):
        if cursor["barrier_count"] == 1:
            prior.append(runs.latest_checkpoint(manifest.run_id).digest)
            pool.processes[1].kill()
            pool.processes[1].join(timeout=1)
        return original(pool, binding, lease, model, cursor, documents)

    monkeypatch.setattr(trainer, "_barrier", kill_rank)
    with pytest.raises(TrainingStateError, match="rank .* failed"):
        trainer.train(manifest, CORPUS, **KWARGS)
    assert runs.state(manifest.run_id) == "failed"
    assert runs.latest_checkpoint(manifest.run_id).digest == prior[0]
    assert runs.checkpoint_payload(runs.latest_checkpoint(manifest.run_id))["cursor"]["barrier_count"] == 1
    _assert_no_ranks()
    monkeypatch.setattr(trainer, "_barrier", original)
    model, artifact = trainer.train(manifest, CORPUS, **KWARGS)
    assert model.model_digest == _serial_mean(manifest).model_digest
    assert artifact.barrier_count == 6
    _assert_no_ranks()


@pytest.mark.skipif(not hasattr(signal, "SIGSTOP"), reason="POSIX stopped-worker failure drill")
def test_stopped_rank_collective_timeout_kills_and_joins_all_workers(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(tmp_path, timeout=2)
    trainer = LocalDataParallelTrainer(datasets, runs)
    original = trainer._barrier
    prior = []
    pids = []

    def stop_rank(pool, binding, lease, model, cursor, documents):
        if cursor["barrier_count"] == 1:
            prior.append(runs.latest_checkpoint(manifest.run_id).digest)
            pids.extend(pool.pids)
            os.kill(pool.pids[1], signal.SIGSTOP)
        return original(pool, binding, lease, model, cursor, documents)

    monkeypatch.setattr(trainer, "_barrier", stop_rank)
    with pytest.raises(TrainingStateError, match="collective timed out"):
        trainer.train(manifest, CORPUS, **KWARGS)
    assert runs.latest_checkpoint(manifest.run_id).digest == prior[0]
    assert runs.state(manifest.run_id) == "failed"
    for pid in pids:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    _assert_no_ranks()


def test_completed_reload_and_retry_are_read_only_and_never_spawn_ranks(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    trainer = LocalDataParallelTrainer(datasets, runs)
    model, artifact = trainer.train(manifest, CORPUS, **KWARGS)
    before = tuple(checkpoint.digest for checkpoint in runs.checkpoints(manifest.run_id))
    datasets.close()
    runs.close()
    datasets = DatasetRegistry(tmp_path / "datasets.sqlite3")
    runs = TrainingRepository(tmp_path / "training.sqlite3")
    trainer = LocalDataParallelTrainer(datasets, runs)

    def forbidden(*args, **kwargs):
        raise AssertionError("completed work must never allocate a worker or perform SGD")

    monkeypatch.setattr(parallel, "_RankPool", forbidden)
    monkeypatch.setattr(NumpyRecurrentLM, "train_document", forbidden)
    for restored, restored_artifact in (
        trainer.load_artifact(manifest.run_id),
        trainer.train(manifest, CORPUS, **KWARGS),
    ):
        assert restored.model_digest == model.model_digest
        assert restored_artifact == artifact
    assert tuple(checkpoint.digest for checkpoint in runs.checkpoints(manifest.run_id)) == before
    assert runs.state(manifest.run_id) == "completed"


def test_finished_checkpoint_restart_completes_without_duplicate_barrier(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    trainer = LocalDataParallelTrainer(datasets, runs)
    original = runs.complete

    def interrupt_terminal(*args, **kwargs):
        raise AbruptStop()

    monkeypatch.setattr(runs, "complete", interrupt_terminal)
    with pytest.raises(AbruptStop):
        trainer.train(manifest, CORPUS, **KWARGS)
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    assert runs.checkpoint_payload(checkpoint)["finished"] is True
    assert runs.state(manifest.run_id) == "running"
    _assert_no_ranks()
    monkeypatch.setattr(runs, "complete", original)

    def forbidden(*args, **kwargs):
        raise AssertionError("finished barrier must not run twice")

    monkeypatch.setattr(parallel, "_RankPool", forbidden)
    model, artifact = trainer.train(manifest, CORPUS, **KWARGS)
    assert model.model_digest == checkpoint.model_digest
    assert artifact.checkpoint_digest == checkpoint.digest
    assert artifact.barrier_count == 6
    assert runs.state(manifest.run_id) == "completed"


@pytest.mark.parametrize(
    "budget",
    [
        {"max_steps": 41},
        {"max_tokens": 41},
        {"max_updates": 9},
        {"max_documents": 9},
        {"max_training_bytes": 31},
        {"max_epochs": 1},
        {"max_corpus_bytes": 19},
        {"max_barriers": 5},
        {"max_processes": 1},
    ],
)
def test_parallel_cumulative_budgets_reject_before_worker_allocation(tmp_path, monkeypatch, budget):
    datasets, runs, manifest, _ = _fixture(tmp_path, budget=budget)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("budget denial must precede worker allocation")

    monkeypatch.setattr(parallel, "_RankPool", forbidden)
    with pytest.raises(TrainingStateError, match="budget"):
        LocalDataParallelTrainer(datasets, runs).train(manifest, CORPUS, **KWARGS)
    assert calls == []
    assert runs._db.execute("SELECT COUNT(*) FROM training_run").fetchone()[0] == 0


@pytest.mark.parametrize(
    "field",
    [
        "targets",
        "rank",
        "rank_type",
        "worker_epoch",
        "worker_pid",
        "document_digest",
        "input_model_digest",
        "updated_model_digest",
    ],
)
def test_malformed_rank_receipt_aborts_barrier_before_commit(tmp_path, monkeypatch, field):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    original = parallel._RankPool.run

    def corrupt(pool, jobs):
        results = original(pool, jobs)
        receipt = results[0]["receipt"]
        if field == "rank_type":
            receipt["rank"] = 0.0
        elif field == "worker_pid":
            receipt[field] = results[1]["receipt"][field]
        elif field.endswith("digest"):
            receipt[field] = "0" * 64
        else:
            receipt[field] += 1
        return results

    monkeypatch.setattr(parallel._RankPool, "run", corrupt)
    with pytest.raises(TrainingStateError, match="rank|barrier"):
        LocalDataParallelTrainer(datasets, runs).train(manifest, CORPUS, **KWARGS)
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    assert checkpoint.step == 0
    assert checkpoint.model_digest == manifest.base_model_digest
    assert len(runs.checkpoints(manifest.run_id)) == 1
    assert runs.state(manifest.run_id) == "failed"
    _assert_no_ranks()


def test_stale_parent_cannot_commit_completed_rank_work_or_fail_replacement(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    trainer = LocalDataParallelTrainer(datasets, runs)
    original = trainer._barrier

    def fence_parent(*args, **kwargs):
        result = original(*args, **kwargs)
        runs.recover(manifest.run_id)
        return result

    monkeypatch.setattr(trainer, "_barrier", fence_parent)
    with pytest.raises(TrainingStateError, match="stale|not running"):
        trainer.train(manifest, CORPUS, **KWARGS)
    assert runs.state(manifest.run_id) == "recovering"
    assert runs.latest_checkpoint(manifest.run_id).step == 0
    _assert_no_ranks()
    monkeypatch.setattr(trainer, "_barrier", original)
    model, _ = trainer.train(manifest, CORPUS, **KWARGS)
    assert model.model_digest == _serial_mean(manifest).model_digest


def test_source_revoked_after_rank_compute_prevents_checkpoint_commit(tmp_path, monkeypatch):
    datasets, runs, manifest, source_digest = _fixture(tmp_path)
    trainer = LocalDataParallelTrainer(datasets, runs)
    original = trainer._barrier

    def revoke(*args, **kwargs):
        result = original(*args, **kwargs)
        datasets.revoke_source_rights(
            source_digest, reason="operator revokes training", command_id="parallel-revoke"
        )
        return result

    monkeypatch.setattr(trainer, "_barrier", revoke)
    with pytest.raises(PermissionError, match="revoked"):
        trainer.train(manifest, CORPUS, **KWARGS)
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    assert checkpoint.step == 0
    assert checkpoint.model_digest == manifest.base_model_digest
    _assert_no_ranks()


def test_completed_parallel_artifact_denies_revoked_source(tmp_path):
    datasets, runs, manifest, source_digest = _fixture(tmp_path)
    trainer = LocalDataParallelTrainer(datasets, runs)
    trainer.train(manifest, CORPUS, **KWARGS)
    datasets.revoke_source_rights(source_digest, reason="withdrawn license", command_id="parallel-revoke")
    with pytest.raises(PermissionError, match="revoked"):
        trainer.load_artifact(manifest.run_id)


def test_startup_interruption_after_actual_process_start_cleans_up_and_resumes(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    original = multiprocessing.context.SpawnProcess.start
    pids = []

    def interrupt_after_spawn(process):
        original(process)
        pids.append(process.pid)
        raise AbruptStop()

    monkeypatch.setattr(multiprocessing.context.SpawnProcess, "start", interrupt_after_spawn)
    with pytest.raises(AbruptStop):
        LocalDataParallelTrainer(datasets, runs).train(manifest, CORPUS, **KWARGS)
    assert pids
    assert runs.latest_checkpoint(manifest.run_id).step == 0
    for pid in pids:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    _assert_no_ranks()
    monkeypatch.setattr(multiprocessing.context.SpawnProcess, "start", original)
    model, _ = LocalDataParallelTrainer(datasets, runs).train(manifest, CORPUS, **KWARGS)
    assert model.model_digest == _serial_mean(manifest).model_digest


def test_ipc_thread_start_interruption_joins_started_threads_and_all_ranks(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    original = threading.Thread.start
    started = []

    def interrupt_after_thread_start(thread):
        original(thread)
        started.append(thread)
        raise AbruptStop()

    monkeypatch.setattr(threading.Thread, "start", interrupt_after_thread_start)
    with pytest.raises(AbruptStop):
        LocalDataParallelTrainer(datasets, runs).train(manifest, CORPUS, **KWARGS)
    assert started
    assert all(not thread.is_alive() for thread in started)
    assert runs.latest_checkpoint(manifest.run_id).step == 0
    _assert_no_ranks()


def test_empty_startup_window_recovers_bound_run_before_initial_checkpoint(tmp_path, monkeypatch):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    original = runs.start

    def interrupt_after_start(run_id):
        original(run_id)
        raise AbruptStop()

    monkeypatch.setattr(runs, "start", interrupt_after_start)
    with pytest.raises(AbruptStop):
        LocalDataParallelTrainer(datasets, runs).train(manifest, CORPUS, **KWARGS)
    assert runs.state(manifest.run_id) == "running"
    assert runs.latest_checkpoint(manifest.run_id) is None
    monkeypatch.setattr(runs, "start", original)
    model, _ = LocalDataParallelTrainer(datasets, runs).train(manifest, CORPUS, **KWARGS)
    assert model.model_digest == _serial_mean(manifest).model_digest
    assert runs.latest_checkpoint(manifest.run_id).worker_epoch == 1


def test_payload_tamper_fails_completed_reload_and_retry(tmp_path):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    trainer = LocalDataParallelTrainer(datasets, runs)
    trainer.train(manifest, CORPUS, **KWARGS)
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    payload = runs.checkpoint_payload(checkpoint)
    payload["barrier"]["ranks"][0]["targets"] += 1
    runs._db.execute(
        "UPDATE training_checkpoint_payload SET payload_json=? WHERE checkpoint_digest=?",
        (json.dumps(payload), checkpoint.digest),
    )
    runs._db.commit()
    with pytest.raises(TrainingStateError, match="payload identity"):
        trainer.load_artifact(manifest.run_id)
    with pytest.raises(TrainingStateError, match="payload identity"):
        trainer.train(manifest, CORPUS, **KWARGS)


@pytest.mark.parametrize("conflict", ["learning_rate", "epochs", "world_size", "budget", "corpus"])
def test_conflicting_completed_retry_never_spawns_ranks(tmp_path, monkeypatch, conflict):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    trainer = LocalDataParallelTrainer(datasets, runs)
    trainer.train(manifest, CORPUS, **KWARGS)
    arguments = dict(KWARGS)
    corpus = CORPUS
    if conflict in {"learning_rate", "epochs"}:
        arguments[conflict] += 1
    elif conflict == "world_size":
        manifest = replace(manifest, world_size=3)
    elif conflict == "budget":
        manifest = replace(manifest, resource_budget={"max_steps": 1000})
    else:
        corpus = (*CORPUS[:-1], "modified")
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("conflicting input cannot allocate ranks")

    monkeypatch.setattr(parallel, "_RankPool", forbidden)
    with pytest.raises((TrainingStateError, ValueError)):
        trainer.train(manifest, corpus, **arguments)
    assert calls == []


def test_materialized_document_partition_identity_rejects_newline_digest_collision(tmp_path, monkeypatch):
    documents = ("a\nb", "c")
    datasets, runs, manifest, _ = _fixture(tmp_path, corpus=documents)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("changed document partitions cannot allocate ranks")

    monkeypatch.setattr(parallel, "_RankPool", forbidden)
    with pytest.raises(ValueError, match="corpus"):
        LocalDataParallelTrainer(datasets, runs).train(manifest, ("a", "b\nc"), **KWARGS)
    assert calls == []


def test_parallel_contract_exhaustively_matches_binding_checkpoint_and_rank_fields(tmp_path):
    contract = json.loads(
        (Path(__file__).parents[2] / "machine/ai_local_data_parallel_training.json").read_text()
    )
    datasets, runs, manifest, _ = _fixture(tmp_path)
    LocalDataParallelTrainer(datasets, runs).train(manifest, CORPUS, **KWARGS)
    binding = runs.execution_binding(manifest.run_id)
    payload = runs.checkpoint_payload(runs.latest_checkpoint(manifest.run_id))
    assert set(binding) - {"schema_version"} == set(contract["binding"]["immutable_fields"])
    assert set(binding["training_config"]) == set(contract["binding"]["training_config_fields"])
    assert set(binding["training_config"]["runtime"]) == set(contract["binding"]["runtime_fields"])
    assert set(payload) == set(contract["resume_payload"]["fields"])
    assert set(payload["cursor"]) == set(contract["resume_payload"]["cursor_fields"])
    assert set(payload["usage"]) == set(contract["resume_payload"]["usage_fields"])
    assert set(payload["optimizer"]) == set(contract["resume_payload"]["optimizer_fields"])
    assert set(payload["barrier"]) == set(contract["resume_payload"]["barrier_fields"])
    assert set(payload["barrier"]["ranks"][0]) == set(contract["resume_payload"]["rank_receipt_fields"])
    assert contract["local_parallel_training_supported"] is True
    assert contract["remote_cluster_training_supported"] is False
    assert contract["production_model_promotion_authorized"] is False

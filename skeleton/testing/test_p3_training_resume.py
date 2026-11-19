from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from skeleton.ai.runtime.inference import ReferenceNGramModel
from skeleton.ai.runtime.training import (
    DataQualityReport,
    DataQualityRule,
    DatasetManifest,
    DatasetRegistry,
    DatasetSplit,
    IngestEnvelope,
    ReferenceLocalTrainer,
    TrainingRepository,
    TrainingRunManifest,
    TrainingStateError,
    TrainingTelemetry,
    WorkerLease,
    corpus_digest,
)
from skeleton.ai.runtime.training.trainer import _step_count

NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)
CORPUS = (
    "alpha beta gamma.",
    "alpha beta delta!",
    "the café opens",
    "cats chase mice",
    "mice chase cheese",
    "alpha beta gamma.",
    "the café closes",
)


class AbruptStop(BaseException):
    """Simulate process death before exception handlers can terminalize a run."""


def _fixture(tmp_path, corpus=CORPUS, *, budget=None, hyperparameters=None):
    datasets = DatasetRegistry(tmp_path / "datasets.sqlite3")
    ingest = IngestEnvelope.from_bytes(
        source_id="fixture://resume",
        payload="\n".join(corpus).encode(),
        parser_version="plain@1",
        classification="internal",
        rights=("training",),
        trusted=True,
        acquired_at=NOW,
    )
    datasets.register_ingest(ingest)
    dataset = DatasetManifest(
        dataset_id="resume-fixture",
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
    run = TrainingRunManifest(
        run_id="resumable-run",
        dataset_digest=dataset.digest,
        base_model_digest=hashlib.sha256(b"empty").hexdigest(),
        code_digest=hashlib.sha256(b"reference-code").hexdigest(),
        environment_digest=hashlib.sha256(b"test-environment").hexdigest(),
        hyperparameters=hyperparameters or {},
        seed=17,
        resource_budget=budget or {"max_steps": sum(_step_count(item) for item in corpus)},
    )
    runs = TrainingRepository(tmp_path / "runs.sqlite3")
    return datasets, runs, run


def _lease(runs, run_id):
    return WorkerLease(
        **json.loads(
            runs._db.execute("SELECT lease_json FROM worker_lease WHERE run_id=?", (run_id,)).fetchone()[0]
        )
    )


@pytest.mark.parametrize("error_type,expected_state", [(RuntimeError, "failed"), (AbruptStop, "running")])
def test_resume_reopen_skips_committed_documents_and_matches_uninterrupted_model(
    tmp_path, monkeypatch, error_type, expected_state
):
    datasets, runs, run = _fixture(tmp_path)
    real_train = ReferenceNGramModel.train
    calls = []

    def interrupted(batch, **kwargs):
        calls.append(tuple(batch))
        if len(calls) == 2:
            raise error_type("injected interruption")
        return real_train(batch, **kwargs)

    monkeypatch.setattr(ReferenceNGramModel, "train", staticmethod(interrupted))
    with pytest.raises(error_type, match="interruption"):
        ReferenceLocalTrainer(datasets, runs).train(run, CORPUS, checkpoint_every_documents=2, now=NOW)
    assert runs.state(run.run_id) == expected_state
    checkpoint = runs.latest_checkpoint(run.run_id)
    assert runs.checkpoint_payload(checkpoint)["cursor"]["document_index"] == 2
    runs.close()
    runs = TrainingRepository(tmp_path / "runs.sqlite3")
    resumed_calls = []

    def resumed(batch, **kwargs):
        resumed_calls.append(tuple(batch))
        return real_train(batch, **kwargs)

    monkeypatch.setattr(ReferenceNGramModel, "train", staticmethod(resumed))
    model, artifact = ReferenceLocalTrainer(datasets, runs).train(
        run,
        CORPUS,
        checkpoint_every_documents=2,
        worker_id="replacement",
        now=NOW,
    )
    expected = real_train(CORPUS, order=2, model_id=model.model_id)
    assert resumed_calls == [CORPUS[2:4], CORPUS[4:6], CORPUS[6:7]]
    assert model.to_dict() == expected.to_dict()
    assert artifact.model_digest == expected.model_digest
    final = runs.latest_checkpoint(run.run_id)
    assert final.worker_epoch == checkpoint.worker_epoch + 1
    assert runs.checkpoint_payload(final)["usage"] == {
        "steps": sum(_step_count(item) for item in CORPUS),
        "documents": len(CORPUS),
        "corpus_bytes": len("\n".join(CORPUS).encode()),
        "batches": 4,
    }


def test_completed_model_reload_and_identical_retry_make_no_model_calls_or_writes(tmp_path, monkeypatch):
    datasets, runs, run = _fixture(tmp_path)
    model, artifact = ReferenceLocalTrainer(datasets, runs).train(run, CORPUS, now=NOW)
    runs.close()
    runs = TrainingRepository(tmp_path / "runs.sqlite3")

    def unexpected(*args, **kwargs):
        raise AssertionError("completed model must be reloaded")

    monkeypatch.setattr(ReferenceNGramModel, "train", staticmethod(unexpected))
    trainer = ReferenceLocalTrainer(datasets, runs)
    writes_before = runs._db.total_changes
    loaded_model, loaded_artifact = trainer.load_artifact(run.run_id)
    retried_model, retried_artifact = trainer.train(run, CORPUS, now=NOW, checkpoint_every_documents=1)
    assert loaded_model.to_dict() == retried_model.to_dict() == model.to_dict()
    assert loaded_artifact == retried_artifact == artifact
    assert runs._db.total_changes == writes_before


def test_crash_after_final_checkpoint_resumes_terminalization_without_training(tmp_path, monkeypatch):
    datasets, runs, run = _fixture(tmp_path)

    def crash(*args, **kwargs):
        raise RuntimeError("crash before terminal commit")

    monkeypatch.setattr(runs, "complete", crash)
    with pytest.raises(RuntimeError, match="terminal commit"):
        ReferenceLocalTrainer(datasets, runs).train(run, CORPUS, now=NOW)
    final = runs.latest_checkpoint(run.run_id)
    assert runs.checkpoint_payload(final)["finished"] is True
    runs.close()
    reopened = TrainingRepository(tmp_path / "runs.sqlite3")
    monkeypatch.setattr(ReferenceNGramModel, "train", staticmethod(crash))
    model, artifact = ReferenceLocalTrainer(datasets, reopened).train(run, CORPUS, now=NOW)
    assert reopened.state(run.run_id) == "completed"
    assert artifact.checkpoint_digest == final.digest
    assert model.model_digest == final.model_digest


@pytest.mark.parametrize("conflict", ["order", "split", "manifest"])
def test_conflicting_completed_retry_is_rejected_before_model_work(tmp_path, monkeypatch, conflict):
    datasets, runs, run = _fixture(tmp_path)
    ReferenceLocalTrainer(datasets, runs).train(run, CORPUS, now=NOW)
    writes_before = runs._db.total_changes

    def unexpected(*args, **kwargs):
        raise AssertionError("immutable retry must fail before model work")

    monkeypatch.setattr(ReferenceNGramModel, "train", staticmethod(unexpected))
    kwargs = (
        {"order": 3} if conflict == "order" else {"split_name": "alternate"} if conflict == "split" else {}
    )
    retried_manifest = replace(run, seed=99) if conflict == "manifest" else run
    with pytest.raises(TrainingStateError, match="immutable"):
        ReferenceLocalTrainer(datasets, runs).train(retried_manifest, CORPUS, now=NOW, **kwargs)
    assert runs.state(run.run_id) == "completed"
    assert runs._db.total_changes == writes_before


def test_registered_byte_digest_cannot_hide_changed_document_boundaries(tmp_path):
    original, drifted = ("a\nb", "c"), ("a", "b\nc")
    assert corpus_digest(original) == corpus_digest(drifted)
    datasets, runs, run = _fixture(tmp_path, original)
    ReferenceLocalTrainer(datasets, runs).train(run, original, now=NOW)
    with pytest.raises(TrainingStateError, match="execution binding is immutable"):
        ReferenceLocalTrainer(datasets, runs).train(run, drifted, now=NOW)


@pytest.mark.parametrize("target", ["payload", "binding", "missing_payload"])
def test_corrupt_or_missing_durable_payload_fails_closed_after_reopen(tmp_path, target):
    datasets, runs, run = _fixture(tmp_path)
    ReferenceLocalTrainer(datasets, runs).train(run, CORPUS, now=NOW)
    if target == "payload":
        runs._db.execute("UPDATE training_checkpoint_payload SET payload_json='{}'")
    elif target == "binding":
        runs._db.execute("UPDATE training_execution_binding SET binding_json='{}'")
    else:
        runs._db.execute("DELETE FROM training_checkpoint_payload")
    runs._db.commit()
    runs.close()
    reopened = TrainingRepository(tmp_path / "runs.sqlite3")
    with pytest.raises(TrainingStateError, match="identity mismatch|payload is missing"):
        ReferenceLocalTrainer(datasets, reopened).load_artifact(run.run_id)
    assert reopened.state(run.run_id) == "completed"


def test_cumulative_batch_budget_cannot_reset_by_restarting(tmp_path, monkeypatch):
    datasets, runs, run = _fixture(tmp_path, budget={"max_batches": 2, "max_steps": 100})
    trainer = ReferenceLocalTrainer(datasets, runs)
    with pytest.raises(TrainingStateError, match="max_batches"):
        trainer.train(run, CORPUS, checkpoint_every_documents=2, now=NOW)
    checkpoint = runs.latest_checkpoint(run.run_id)
    assert runs.checkpoint_payload(checkpoint)["usage"]["batches"] == 2
    assert runs.checkpoint_payload(checkpoint)["cursor"]["document_index"] == 4
    runs.close()
    reopened = TrainingRepository(tmp_path / "runs.sqlite3")

    def unexpected(*args, **kwargs):
        raise AssertionError("exhausted budget must fail before allocating model work")

    monkeypatch.setattr(ReferenceNGramModel, "train", staticmethod(unexpected))
    with pytest.raises(TrainingStateError, match="max_batches"):
        ReferenceLocalTrainer(datasets, reopened).train(run, CORPUS, checkpoint_every_documents=16, now=NOW)
    assert reopened.latest_checkpoint(run.run_id).digest == checkpoint.digest


def test_step_budget_counts_punctuation_and_document_end_before_execution(tmp_path):
    corpus = ("word!!!!!",)
    datasets, runs, run = _fixture(tmp_path, corpus, budget={"max_steps": 1})
    with pytest.raises(TrainingStateError, match="max_steps"):
        ReferenceLocalTrainer(datasets, runs).train(run, corpus, now=NOW)
    with pytest.raises(KeyError):
        runs.state(run.run_id)


def test_replacement_epoch_fences_checkpoint_telemetry_failure_and_completion(tmp_path, monkeypatch):
    datasets, old_repo, run = _fixture(tmp_path)

    def stop(*args, **kwargs):
        raise AbruptStop("hard process stop")

    monkeypatch.setattr(ReferenceNGramModel, "train", staticmethod(stop))
    with pytest.raises(AbruptStop):
        ReferenceLocalTrainer(datasets, old_repo).train(run, CORPUS, now=NOW)
    old_lease = _lease(old_repo, run.run_id)
    checkpoint = old_repo.latest_checkpoint(run.run_id)
    payload = old_repo.checkpoint_payload(checkpoint)
    replacement = TrainingRepository(tmp_path / "runs.sqlite3")
    replacement.recover(run.run_id)
    replacement.start(run.run_id)
    replacement.lease_worker(run.run_id, "replacement", issued_at=NOW)
    for operation in (
        lambda: old_repo.checkpoint(replace(checkpoint, step=1), old_lease, payload=payload),
        lambda: old_repo.record_telemetry(
            TrainingTelemetry(run.run_id, 0, {"stale": 1.0}, NOW.isoformat()), old_lease
        ),
        lambda: old_repo.fail(run.run_id, old_lease),
        lambda: old_repo.complete(run.run_id, old_lease),
    ):
        with pytest.raises(TrainingStateError, match="stale worker epoch"):
            operation()
    for operation in (
        lambda: old_repo.fail(run.run_id),
        lambda: old_repo.complete(run.run_id),
        lambda: old_repo.record_telemetry(
            TrainingTelemetry(run.run_id, 0, {"unleased": 1.0}, NOW.isoformat())
        ),
    ):
        with pytest.raises(TrainingStateError, match="requires a worker lease"):
            operation()
    assert replacement.state(run.run_id) == "running"
    assert replacement.latest_checkpoint(run.run_id).digest == checkpoint.digest


def test_payload_insert_failure_rolls_back_checkpoint_metadata_atomically(tmp_path, monkeypatch):
    datasets, runs, run = _fixture(tmp_path)
    original_checkpoint = runs.checkpoint

    def checkpoint_with_storage_failure(checkpoint, lease, **kwargs):
        if checkpoint.step > 0:
            runs._db.execute(
                """CREATE TEMP TRIGGER reject_payload BEFORE INSERT ON training_checkpoint_payload
                BEGIN SELECT RAISE(ABORT, 'injected payload storage failure'); END"""
            )
            runs._db.commit()
        return original_checkpoint(checkpoint, lease, **kwargs)

    monkeypatch.setattr(runs, "checkpoint", checkpoint_with_storage_failure)
    with pytest.raises(sqlite3.IntegrityError, match="payload storage failure"):
        ReferenceLocalTrainer(datasets, runs).train(run, CORPUS, now=NOW)
    assert runs.latest_checkpoint(run.run_id).step == 0
    assert runs._db.execute("SELECT COUNT(*) FROM training_checkpoint").fetchone()[0] == 1
    assert runs._db.execute("SELECT COUNT(*) FROM training_checkpoint_payload").fetchone()[0] == 1


@pytest.mark.parametrize("value", [0, -1, True, 4097, 1.5])
def test_checkpoint_batch_bound_rejects_invalid_sizes_before_registration(tmp_path, value):
    datasets, runs, run = _fixture(tmp_path)
    with pytest.raises(ValueError, match="checkpoint_every_documents"):
        ReferenceLocalTrainer(datasets, runs).train(run, CORPUS, checkpoint_every_documents=value, now=NOW)
    with pytest.raises(KeyError):
        runs.state(run.run_id)


def test_resume_restores_checkpoint_committed_during_recovery_race(tmp_path, monkeypatch):
    datasets, runs, run = _fixture(tmp_path)
    real_train = ReferenceNGramModel.train
    calls = 0

    def stop_second(batch, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise AbruptStop("pause")
        return real_train(batch, **kwargs)

    monkeypatch.setattr(ReferenceNGramModel, "train", staticmethod(stop_second))
    trainer = ReferenceLocalTrainer(datasets, runs)
    with pytest.raises(AbruptStop):
        trainer.train(run, CORPUS, checkpoint_every_documents=2, now=NOW)
    lease = _lease(runs, run.run_id)
    binding = runs.execution_binding(run.run_id)
    real_recover = runs.recover

    def recovery_after_worker_checkpoint(run_id, **kwargs):
        model = real_train(CORPUS[:4], order=2, model_id=binding["model_config"]["model_id"])
        trainer._persist(
            run,
            binding,
            lease,
            model,
            {
                "steps": sum(_step_count(item) for item in CORPUS[:4]),
                "documents": 4,
                "corpus_bytes": len("\n".join(CORPUS[:4]).encode()),
                "batches": 2,
            },
            NOW,
        )
        return real_recover(run_id, **kwargs)

    monkeypatch.setattr(runs, "recover", recovery_after_worker_checkpoint)
    resumed_batches = []

    def record(batch, **kwargs):
        resumed_batches.append(tuple(batch))
        return real_train(batch, **kwargs)

    monkeypatch.setattr(ReferenceNGramModel, "train", staticmethod(record))
    model, _ = trainer.train(run, CORPUS, checkpoint_every_documents=2, now=NOW)
    assert resumed_batches == [CORPUS[4:6], CORPUS[6:]]
    assert model.to_dict() == real_train(CORPUS, order=2, model_id=model.model_id).to_dict()


def test_failed_sqlite_commit_rolls_back_and_keeps_repository_usable(tmp_path):
    datasets, runs, run = _fixture(tmp_path)
    runs.register_run(run, datasets, created_at=NOW)
    reader = sqlite3.connect(tmp_path / "runs.sqlite3")
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT state FROM training_run").fetchall()
        runs._db.execute("PRAGMA busy_timeout=1")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            runs.start(run.run_id)
        assert runs._db.in_transaction is False
        assert runs.state(run.run_id) == "registered"
        reader.rollback()
        runs.start(run.run_id)
        assert runs.state(run.run_id) == "running"
    finally:
        reader.close()


def test_hard_document_bound_fails_before_run_registration(tmp_path):
    corpus = ("a" * (1024 * 1024 + 1),)
    datasets, runs, run = _fixture(tmp_path, corpus)
    with pytest.raises(TrainingStateError, match="document byte limit"):
        ReferenceLocalTrainer(datasets, runs).train(run, corpus, now=NOW)
    with pytest.raises(KeyError):
        runs.state(run.run_id)


@pytest.mark.parametrize("crash_point", ["lease", "initial_checkpoint"])
def test_restart_before_initial_checkpoint_safely_recovers_cursor_zero(tmp_path, monkeypatch, crash_point):
    datasets, runs, run = _fixture(tmp_path)

    def stop(*args, **kwargs):
        raise AbruptStop("initial checkpoint window")

    monkeypatch.setattr(runs, "lease_worker" if crash_point == "lease" else "checkpoint", stop)
    with pytest.raises(AbruptStop, match="initial checkpoint window"):
        ReferenceLocalTrainer(datasets, runs).train(run, CORPUS, now=NOW)
    assert runs.state(run.run_id) == "running"
    assert runs.latest_checkpoint(run.run_id) is None
    runs.close()
    reopened = TrainingRepository(tmp_path / "runs.sqlite3")
    model, artifact = ReferenceLocalTrainer(datasets, reopened).train(run, CORPUS, now=NOW)
    assert reopened.state(run.run_id) == "completed"
    assert reopened.latest_checkpoint(run.run_id).worker_epoch == 1
    assert (
        artifact.model_digest
        == ReferenceNGramModel.train(CORPUS, order=2, model_id=model.model_id).model_digest
    )

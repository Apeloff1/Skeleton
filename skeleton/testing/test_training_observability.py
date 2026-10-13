from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from skeleton.ai.runtime.training.control import (
    TrainingRepository,
    TrainingRunManifest,
    TrainingTelemetry,
    WorkerLease,
    _canonical,
    _digest,
)
from skeleton.ai.runtime.training.data import (
    DatasetRegistry,
    IngestEnvelope,
    MaterializedTrainingSource,
)
from skeleton.ai.runtime.training.neural_trainer import NeuralLocalTrainer
from skeleton.ai.runtime.training.observability import (
    TrainingObservationError,
    TrainingObserver,
)
from skeleton.ai.runtime.training.trainer import ReferenceLocalTrainer

NOW = datetime(2026, 10, 4, 18, tzinfo=UTC)
CORPUS = ("aba", "abc", "café")


def _fixture(tmp_path, kind="neural"):
    datasets = DatasetRegistry(tmp_path / "datasets.sqlite3")
    raw = json.dumps(list(CORPUS), ensure_ascii=False).encode()
    envelope = IngestEnvelope.from_bytes(
        source_id="fixture://training-observation",
        payload=raw,
        parser_version="json-documents@1",
        classification="internal",
        rights=("training",),
        trusted=True,
        acquired_at=NOW,
    )
    receipt = datasets.ingest_materialized(
        ingestion_id="observation-ingest",
        dataset_id="observation-data",
        expected_version=0,
        sources={"train": (MaterializedTrainingSource(envelope, raw, "json_documents", ("license:test",)),)},
        classification="internal",
        permitted_uses=("training",),
        retention_class="test",
    )
    runs = TrainingRepository(tmp_path / "runs.sqlite3")
    base = NeuralLocalTrainer.initialize_model("observed-run", hidden_size=4, seed=7)
    manifest = TrainingRunManifest(
        run_id="observed-run",
        dataset_digest=receipt.dataset_digest,
        base_model_digest=base.model_digest if kind != "reference" else _digest("empty-reference"),
        code_digest=_digest("observer-test-code"),
        environment_digest=_digest("observer-test-env"),
        hyperparameters={},
        seed=7,
        world_size=2 if kind == "parallel" else 1,
        parallelism="data_parallel" if kind == "parallel" else "single",
        resource_budget={
            "max_steps": 100,
            "max_documents": 20,
            "max_corpus_bytes": 100,
            "max_training_bytes": 100,
            "declared_unknown": 99,
        },
    )
    return datasets, runs, manifest, envelope


def _train(datasets, runs, manifest, kind="neural", *, now=NOW):
    if kind == "reference":
        return ReferenceLocalTrainer(datasets, runs).train(
            manifest, CORPUS, checkpoint_every_documents=1, now=now
        )
    if kind == "parallel":
        from skeleton.ai.runtime.training.distributed_trainer import (
            LocalDataParallelTrainer,
        )

        trainer = LocalDataParallelTrainer(datasets, runs)
    else:
        trainer = NeuralLocalTrainer(datasets, runs)
    return trainer.train(
        manifest, CORPUS, hidden_size=4, epochs=2, learning_rate=0.2, gradient_clip=1, now=now
    )


def _rewrite_checkpoint(runs, checkpoint, *, payload=None, **changes):
    if payload is not None:
        changes["payload_digest"] = _digest(payload)
    revised = replace(checkpoint, **changes)
    original = runs.checkpoint_payload(checkpoint)
    with runs._write():
        runs._db.execute(
            "DELETE FROM training_checkpoint_payload WHERE checkpoint_digest=?", (checkpoint.digest,)
        )
        runs._db.execute(
            "UPDATE training_checkpoint SET checkpoint_digest=?,checkpoint_json=? WHERE checkpoint_digest=?",
            (revised.digest, _canonical(revised.as_dict()), checkpoint.digest),
        )
        value = original if payload is None else payload
        runs._db.execute(
            "INSERT INTO training_checkpoint_payload VALUES (?,?,?)",
            (revised.digest, revised.payload_digest, _canonical(value)),
        )
    return revised


@pytest.mark.parametrize("kind", ["reference", "neural", "parallel"])
def test_committed_observation_matches_real_work_is_read_only_and_restart_stable(tmp_path, kind):
    datasets, runs, manifest, _ = _fixture(tmp_path, kind)
    model, artifact = _train(datasets, runs, manifest, kind)
    changes = runs._db.total_changes
    observer = TrainingObserver(runs, datasets)
    report = observer.snapshot(
        manifest.run_id,
        now=NOW + timedelta(seconds=10),
        expected_code_digest=manifest.code_digest,
        expected_environment_digest=manifest.environment_digest,
    )
    result = report.as_dict()
    assert runs._db.total_changes == changes
    assert result["state"] == "completed"
    terminal = result["checkpoints"][-1]
    assert terminal["model_digest"] == model.model_digest == artifact.model_digest
    assert terminal["checkpoint_digest"] == artifact.checkpoint_digest
    assert terminal["semantic_validation"] == "verified_exact_corpus"
    assert terminal["finished"] is True
    assert result["source"]["exact_materialized_corpus"] is True
    assert result["throughput"]["documents_per_second"] is None
    assert result["throughput"]["available"] is False
    assert result["activity"]["checkpoint_idle_seconds"] == 10
    assert not any(worker["write_state_eligible"] for worker in result["workers"])
    assert result["promotion_authority"] is False
    budget = {item["name"]: item for item in result["budgets"]}
    assert budget["max_steps"]["used"] == terminal["usage"]["steps"]
    assert budget["max_steps"]["fraction"] == terminal["usage"]["steps"] / 100
    assert budget["declared_unknown"]["available"] is False
    if kind == "reference":
        assert terminal["loss"]["available"] is False
    else:
        assert terminal["loss"]["initial"] == artifact.initial_loss
        assert terminal["loss"]["final"] == artifact.final_loss
    if kind == "parallel":
        assert len({rank["worker_pid"] for rank in terminal["barrier"]["ranks"]}) == 2
        assert terminal["usage"]["barriers"] == 4
    assert all(event["worker_epoch"] is None for event in result["events"])
    assert all(not event["unverified_metric_names"] for event in result["events"])
    serialized = _canonical(result)
    assert '"model":' not in serialized and '"embedding":' not in serialized
    assert "café" not in serialized
    runs.close()
    datasets.close()
    reopened_runs = TrainingRepository(tmp_path / "runs.sqlite3")
    reopened_data = DatasetRegistry(tmp_path / "datasets.sqlite3")
    assert (
        TrainingObserver(reopened_runs, reopened_data)
        .snapshot(
            manifest.run_id,
            now=NOW + timedelta(seconds=10),
            expected_code_digest=manifest.code_digest,
            expected_environment_digest=manifest.environment_digest,
        )
        .digest
        == report.digest
    )
    mutated = report.as_dict()
    mutated["state"] = "fake"
    assert report.as_dict()["state"] == "completed"


def test_bounded_window_reports_partial_history_without_inventing_rates(tmp_path):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    result = TrainingObserver(runs, datasets).snapshot(manifest.run_id, now=NOW, max_points=2).as_dict()
    assert len(result["checkpoints"]) == len(result["events"]) == 2
    assert result["window"]["live_checkpoint_count"] == 7
    assert result["window"]["all_live_checkpoints_selected"] is False
    assert result["throughput"]["available"] is False
    assert len({point["created_at"] for point in result["checkpoints"]}) == 1


def test_actual_preference_report_names_dpo_loss_margin_and_counts_pairs(tmp_path):
    from skeleton.testing.test_local_preference_training import CONFIG
    from skeleton.testing.test_local_preference_training import (
        _fixture as preference_fixture,
    )

    fixture = preference_fixture(tmp_path)
    datasets, runs, trainer, original, experiment, _, _ = fixture
    manifest = replace(
        original,
        resource_budget={
            "max_pairs": 18,
            "max_documents": 18,
            "max_steps": 10000,
            "max_training_bytes": 10000,
        },
    )
    _, artifact = trainer.train(
        manifest, datasets.training_corpus(manifest.dataset_digest), experiment=experiment, **CONFIG, now=NOW
    )
    report = TrainingObserver(runs, datasets).snapshot(manifest.run_id, now=NOW, max_points=3).as_dict()
    point = report["checkpoints"][-1]
    assert point["semantic_validation"] == "verified_exact_corpus"
    assert point["loss"]["kind"] == "dpo_logistic_preference"
    assert point["loss"]["initial"] == artifact.initial_loss
    assert point["loss"]["final"] == artifact.final_loss
    assert point["preference_observations"]["initial"]["margin"] == artifact.initial_margin
    assert point["preference_observations"]["final"]["margin"] == artifact.final_margin
    assert point["preference_observations"]["reference_model_digest"] == artifact.reference_model_digest
    assert point["usage"]["pairs"] == 18
    assert point["usage"]["evaluation_steps"] > 0
    assert "documents" not in point["usage"]
    budgets = {item["name"]: item for item in report["budgets"]}
    assert budgets["max_pairs"]["used"] == budgets["max_documents"]["used"] == 18
    assert all(not event["unverified_metric_names"] for event in report["events"])
    assert report["throughput"]["available"] is False


def test_real_interruption_idle_alert_recovery_epoch_and_resume_are_distinguished(tmp_path, monkeypatch):
    from skeleton.ai.runtime.inference.neural import NumpyRecurrentLM

    class AbruptStop(BaseException):
        pass

    datasets, runs, manifest, _ = _fixture(tmp_path)
    original = NumpyRecurrentLM.train_document
    updates = 0

    def interrupt(self, *args, **kwargs):
        nonlocal updates
        updates += 1
        if updates == 3:
            raise AbruptStop
        return original(self, *args, **kwargs)

    monkeypatch.setattr(NumpyRecurrentLM, "train_document", interrupt)
    with pytest.raises(AbruptStop):
        _train(datasets, runs, manifest)
    observer = TrainingObserver(runs, datasets)
    idle = observer.snapshot(manifest.run_id, now=NOW + timedelta(seconds=301)).as_dict()
    assert idle["state"] == "running"
    assert [alert["kind"] for alert in idle["alerts"]] == ["training_stalled"]
    assert idle["checkpoints"][-1]["usage"]["documents"] == 2
    old = runs._db.execute("SELECT lease_json FROM worker_lease").fetchone()[0]
    runs.recover(manifest.run_id)
    recovery = observer.snapshot(manifest.run_id, now=NOW + timedelta(seconds=302)).as_dict()
    assert recovery["worker_epoch"] == 1
    assert recovery["workers"] == []
    assert [alert["kind"] for alert in recovery["alerts"]] == ["recovery_pending"]
    # A stale recorded row is observable but never eligible to write.
    lease = WorkerLease(**json.loads(old))
    with runs._write():
        runs._db.execute(
            "INSERT INTO worker_lease VALUES (?,?,?,?)", (lease.run_id, lease.worker_id, lease.epoch, old)
        )
    stale = observer.snapshot(manifest.run_id, now=NOW + timedelta(seconds=302)).as_dict()
    assert stale["workers"][0]["epoch_status"] == "stale"
    assert not stale["workers"][0]["write_state_eligible"]
    assert "worker_epoch_stale" in [alert["kind"] for alert in stale["alerts"]]
    monkeypatch.setattr(NumpyRecurrentLM, "train_document", original)
    _train(datasets, runs, manifest, now=NOW + timedelta(seconds=303))
    resumed = observer.snapshot(manifest.run_id, now=NOW + timedelta(seconds=304)).as_dict()
    assert resumed["state"] == "completed"
    assert resumed["worker_epoch"] == resumed["checkpoints"][-1]["worker_epoch"] == 1
    assert resumed["checkpoints"][-1]["usage"]["documents"] == 6
    assert resumed["activity"]["recovery_transition_history_available"] is False
    assert "recovery_pending" not in [alert["kind"] for alert in resumed["alerts"]]


@pytest.mark.parametrize("change", ["cursor", "model_nan", "future", "epoch", "model_digest"])
def test_digest_reissued_checkpoint_tamper_cannot_be_reported_as_measured(tmp_path, change):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    payload = runs.checkpoint_payload(checkpoint)
    if change == "cursor":
        payload["cursor"]["document_index"] = 1
        _rewrite_checkpoint(runs, checkpoint, payload=payload, data_cursor_digest=_digest(payload["cursor"]))
    elif change == "model_nan":
        with runs._write():
            runs._db.execute(
                "UPDATE training_checkpoint_payload SET payload_json=? WHERE checkpoint_digest=?",
                (
                    _canonical(payload).replace('"initial_loss":', '"initial_loss":NaN,"forged":'),
                    checkpoint.digest,
                ),
            )
    elif change == "future":
        _rewrite_checkpoint(runs, checkpoint, created_at=(NOW + timedelta(seconds=1)).isoformat())
    elif change == "epoch":
        _rewrite_checkpoint(runs, checkpoint, worker_epoch=1)
    else:
        _rewrite_checkpoint(runs, checkpoint, model_digest=_digest("forged-model"))
    changes = runs._db.total_changes
    with pytest.raises(TrainingObservationError):
        TrainingObserver(runs, datasets).snapshot(manifest.run_id, now=NOW)
    assert runs._db.total_changes == changes


@pytest.mark.parametrize("kind", ["wrong_counter", "future_step", "regressed_time", "bool_metric"])
def test_telemetry_content_identity_and_timeline_are_checked(tmp_path, kind):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    event = TrainingTelemetry(
        manifest.run_id, checkpoint.step, {"sgd_updates": 99}, NOW.isoformat()
    ).as_dict()
    if kind == "future_step":
        event["step"] += 1
    elif kind == "regressed_time":
        event["emitted_at"] = (NOW - timedelta(seconds=1)).isoformat()
    elif kind == "bool_metric":
        event["metrics"]["sgd_updates"] = True
    with runs._write():
        runs._db.execute(
            "INSERT INTO training_telemetry VALUES (?,?,?,?)",
            (_digest(event), manifest.run_id, event["step"], _canonical(event)),
        )
    with pytest.raises(TrainingObservationError):
        TrainingObserver(runs, datasets).snapshot(manifest.run_id, now=NOW)


def test_unknown_telemetry_is_recorded_but_not_promoted_to_measurement(tmp_path):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    event = TrainingTelemetry(
        manifest.run_id, checkpoint.step, {"loss": 0, "throughput": 1e9}, NOW.isoformat()
    )
    with runs._write():
        runs._db.execute(
            "INSERT INTO training_telemetry VALUES (?,?,?,?)",
            (event.digest, manifest.run_id, event.step, _canonical(event.as_dict())),
        )
    observed = TrainingObserver(runs, datasets).snapshot(manifest.run_id, now=NOW).as_dict()["events"][-1]
    assert observed["verified_counters"] == {}
    assert observed["unverified_metric_names"] == ["loss", "throughput"]


def test_source_withdrawal_and_expected_identity_fences(tmp_path):
    datasets, runs, manifest, envelope = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    observer = TrainingObserver(runs, datasets)
    with pytest.raises(TrainingObservationError, match="identity"):
        observer.snapshot(manifest.run_id, now=NOW, expected_code_digest=_digest("other-code"))
    with pytest.raises(TrainingObservationError, match="identity"):
        observer.snapshot(manifest.run_id, now=NOW, expected_environment_digest=_digest("other-runtime"))
    datasets.revoke_source_rights(
        envelope.content_digest, reason="fixture withdrawal", command_id="withdraw-observed"
    )
    with pytest.raises(TrainingObservationError):
        observer.snapshot(manifest.run_id, now=NOW)


@pytest.mark.parametrize("target", ["payload", "aggregate", "event", "metadata"])
def test_byte_admission_rejects_before_fetching_oversized_state(tmp_path, monkeypatch, target):
    from skeleton.ai.runtime.training import observability

    datasets, runs, manifest, _ = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    constant = {
        "payload": "MAX_PAYLOAD_BYTES",
        "aggregate": "MAX_SELECTED_PAYLOAD_BYTES",
        "event": "MAX_EVENT_BYTES",
        "metadata": "MAX_METADATA_BYTES",
    }[target]
    monkeypatch.setattr(observability, constant, 1)
    with pytest.raises(TrainingObservationError, match="bounds"):
        TrainingObserver(runs, datasets).snapshot(manifest.run_id, now=NOW)


def test_uncommitted_caller_state_is_never_observed_or_rolled_back(tmp_path):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    runs._db.execute("UPDATE training_run SET state='failed' WHERE run_id=?", (manifest.run_id,))
    with pytest.raises(TrainingObservationError, match="committed"):
        TrainingObserver(runs, datasets).snapshot(manifest.run_id, now=NOW)
    assert runs._db.in_transaction
    runs._db.rollback()
    assert runs.state(manifest.run_id) == "completed"


def test_retained_archive_gaps_do_not_claim_verified_event_checkpoint_associations(tmp_path):
    from skeleton.ai.runtime.training.checkpoint_archive import (
        TrainingCheckpointArchive,
    )
    from skeleton.storage.cas import GovernedContentStore

    datasets, runs, manifest, _ = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    archive = TrainingCheckpointArchive(
        runs, GovernedContentStore(tmp_path / "cas.sqlite3"), tenant_id="test", trust_context="internal"
    )
    checkpoints = runs.checkpoints(manifest.run_id)
    for checkpoint in checkpoints:
        archive.backup(manifest.run_id, datasets, CORPUS, checkpoint_digest=checkpoint.digest)
    archive.pin(manifest.run_id, checkpoints[-1].digest, "keep-initial")
    removed = archive.retain(manifest.run_id, keep_newest=1)
    assert len(removed) == 5
    report = TrainingObserver(runs, datasets).snapshot(manifest.run_id, now=NOW).as_dict()
    assert report["window"]["live_checkpoint_count"] == 2
    assert report["window"]["archived_history_verified"] is False
    missing = [
        event
        for event in report["events"]
        if event["checkpoint_association"] == "unavailable_missing_live_checkpoint"
    ]
    assert len(missing) == 5
    assert all(event["verified_counters"] == {} and event["checkpoint_digest"] is None for event in missing)


def test_elastic_observation_distinguishes_real_physical_workers_from_logical_ranks(tmp_path):
    from skeleton.ai.runtime.training.elastic_trainer import ElasticLocalTrainer
    from skeleton.testing.test_elastic_training_recovery import CORPUS as elastic_corpus
    from skeleton.testing.test_elastic_training_recovery import KWARGS
    from skeleton.testing.test_elastic_training_recovery import (
        _fixture as elastic_fixture,
    )

    datasets, runs, manifest, _ = elastic_fixture(tmp_path)
    _, artifact = ElasticLocalTrainer(datasets, runs).train(
        manifest, elastic_corpus, physical_workers=1, **KWARGS
    )
    result = TrainingObserver(runs, datasets).snapshot(manifest.run_id, now=NOW).as_dict()
    point = result["checkpoints"][-1]
    membership = point["barrier"]["membership"]
    assert membership["physical_workers"] == artifact.physical_workers == 1
    assert membership["resize_count"] == artifact.membership_change_count == 0
    assert membership["digest"] == artifact.membership_receipt_digest
    assert point["barrier"]["world_size"] == 4
    assert len({rank["worker_pid"] for rank in point["barrier"]["ranks"]}) == 1
    assert next(item for item in result["budgets"] if item["name"] == "max_processes")["used"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("document_count", True),
        ("corpus_bytes", 100),
        ("schema_version", "unknown"),
        ("split_digest", "f" * 64),
    ],
)
def test_reissued_binding_still_requires_exact_corpus_geometry(tmp_path, field, value):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    binding = runs.execution_binding(manifest.run_id)
    binding[field] = value
    with runs._write():
        runs._db.execute(
            "UPDATE training_execution_binding SET binding_digest=?,binding_json=? WHERE run_id=?",
            (_digest(binding), _canonical(binding), manifest.run_id),
        )
    with pytest.raises(TrainingObservationError):
        TrainingObserver(runs, datasets).snapshot(manifest.run_id, now=NOW)


def test_reissued_manifest_and_checkpoint_graph_cannot_hide_budget_overrun(tmp_path):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    checkpoint_payloads = [
        (checkpoint, runs.checkpoint_payload(checkpoint)) for checkpoint in runs.checkpoints(manifest.run_id)
    ]
    revised = replace(manifest, resource_budget={"max_steps": 0})
    binding = runs.execution_binding(manifest.run_id)
    binding["manifest_digest"] = revised.digest
    with runs._write():
        runs._db.execute(
            "UPDATE training_run SET manifest_digest=?,manifest_json=? WHERE run_id=?",
            (revised.digest, _canonical(revised.as_dict()), manifest.run_id),
        )
        runs._db.execute(
            "UPDATE training_execution_binding SET binding_digest=?,binding_json=? WHERE run_id=?",
            (_digest(binding), _canonical(binding), manifest.run_id),
        )
        for checkpoint, payload in checkpoint_payloads:
            payload["binding_digest"] = _digest(binding)
            new = replace(checkpoint, manifest_digest=revised.digest, payload_digest=_digest(payload))
            runs._db.execute(
                "DELETE FROM training_checkpoint_payload WHERE checkpoint_digest=?", (checkpoint.digest,)
            )
            runs._db.execute(
                "UPDATE training_checkpoint SET checkpoint_digest=?,checkpoint_json=? WHERE checkpoint_digest=?",
                (new.digest, _canonical(new.as_dict()), checkpoint.digest),
            )
            runs._db.execute(
                "INSERT INTO training_checkpoint_payload VALUES (?,?,?)",
                (new.digest, new.payload_digest, _canonical(payload)),
            )
    with pytest.raises(TrainingObservationError) as caught:
        TrainingObserver(runs, datasets).snapshot(manifest.run_id, now=NOW)
    assert "budget exceeded" in str(caught.value.__cause__)


@pytest.mark.parametrize("target", ["checkpoint", "event"])
def test_recent_window_checks_its_immediate_timeline_predecessor(tmp_path, target):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    if target == "checkpoint":
        _rewrite_checkpoint(
            runs, runs.checkpoints(manifest.run_id)[1], created_at=(NOW + timedelta(seconds=5)).isoformat()
        )
    else:
        rowid, old_digest, encoded = runs._db.execute(
            "SELECT rowid,telemetry_digest,telemetry_json FROM training_telemetry ORDER BY rowid DESC LIMIT 1 OFFSET 1"
        ).fetchone()
        event = json.loads(encoded)
        event["emitted_at"] = (NOW + timedelta(seconds=5)).isoformat()
        with runs._write():
            runs._db.execute(
                "UPDATE training_telemetry SET telemetry_digest=?,telemetry_json=? WHERE rowid=? AND telemetry_digest=?",
                (_digest(event), _canonical(event), rowid, old_digest),
            )
    with pytest.raises(TrainingObservationError, match="timeline"):
        TrainingObserver(runs, datasets).snapshot(
            manifest.run_id, now=NOW + timedelta(seconds=10), max_points=1
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_points": True},
        {"max_points": 4097},
        {"stall_seconds": 0},
        {"stall_seconds": float("nan")},
        {"stall_seconds": 10**1000},
        {"now": NOW.replace(tzinfo=None)},
    ],
)
def test_invalid_observation_request_has_no_state_effect(tmp_path, kwargs):
    datasets, runs, manifest, _ = _fixture(tmp_path)
    runs.register_run(manifest, datasets, created_at=NOW)
    changes = runs._db.total_changes
    with pytest.raises(ValueError):
        TrainingObserver(runs, datasets).snapshot(manifest.run_id, **({"now": NOW} | kwargs))
    assert runs._db.total_changes == changes

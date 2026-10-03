from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math

import pytest

from skeleton.ai.runtime.training import (
    DataQualityReport,
    DataQualityRule,
    DatasetManifest,
    DatasetRegistry,
    DatasetSplit,
    IngestEnvelope,
    TrainingCheckpoint,
    TrainingRepository,
    TrainingRunManifest,
    TrainingStateError,
    TrainingTelemetry,
)


NOW=datetime(2026,10,2,9,0,tzinfo=timezone.utc)


def _digest(text:str)->str:
    return hashlib.sha256(text.encode()).hexdigest()


def _dataset(tmp_path):
    registry=DatasetRegistry(tmp_path/"dataset.sqlite3")
    ingest=IngestEnvelope.from_bytes(
        source_id="fixture://train",
        payload=b"stable corpus",
        parser_version="parser@1",
        classification="internal",
        rights=("training",),
        trusted=True,
        acquired_at=NOW,
    )
    registry.register_ingest(ingest)
    manifest=DatasetManifest(
        dataset_id="core",
        version="1",
        splits=(DatasetSplit("train",_digest("split"),64),),
        source_ingest_digests=(ingest.content_digest,),
        classification="internal",
        permitted_uses=("training",),
        retention_class="model-development",
        parser_versions=("parser@1",),
    )
    registry.register_dataset(manifest)
    registry.record_quality(DataQualityReport.evaluate(
        manifest.digest,
        (DataQualityRule("validity","valid_fraction",">=",0.99),),
        {"valid_fraction":1.0},
    ))
    return registry,manifest


def _manifest(dataset_digest:str)->TrainingRunManifest:
    return TrainingRunManifest(
        run_id="run-001",
        dataset_digest=dataset_digest,
        base_model_digest=_digest("base-model"),
        code_digest=_digest("trainer-code"),
        environment_digest=_digest("python-env"),
        hyperparameters={"learning_rate":0.001,"batch_size":8},
        seed=17,
        world_size=2,
        parallelism="data_parallel",
        collective_timeout_seconds=15,
        resource_budget={"max_steps":1000,"max_gpu_hours":4},
    )


def _checkpoint(manifest:TrainingRunManifest,lease,step:int,model:str)->TrainingCheckpoint:
    return TrainingCheckpoint(
        run_id=manifest.run_id,
        manifest_digest=manifest.digest,
        step=step,
        model_digest=_digest(model),
        optimizer_digest=_digest(f"opt-{step}"),
        rng_digest=_digest(f"rng-{step}"),
        data_cursor_digest=_digest(f"cursor-{step}"),
        worker_epoch=lease.epoch,
        created_at=NOW.isoformat(),
    )


def test_training_run_requires_quality_gated_registered_dataset(tmp_path):
    datasets,manifest=_dataset(tmp_path)
    repo=TrainingRepository(tmp_path/"training.sqlite3")
    run=_manifest(manifest.digest)
    assert repo.register_run(run,datasets,created_at=NOW)==run.digest
    assert repo.manifest(run.run_id).digest==run.digest
    assert repo.state(run.run_id)=="registered"


def test_training_run_identity_is_immutable(tmp_path):
    datasets,manifest=_dataset(tmp_path)
    repo=TrainingRepository(tmp_path/"training.sqlite3")
    run=_manifest(manifest.digest)
    repo.register_run(run,datasets,created_at=NOW)
    changed=TrainingRunManifest(
        run_id=run.run_id,
        dataset_digest=run.dataset_digest,
        base_model_digest=run.base_model_digest,
        code_digest=run.code_digest,
        environment_digest=run.environment_digest,
        hyperparameters={"learning_rate":0.9},
        seed=run.seed,
    )
    with pytest.raises(TrainingStateError,match="immutable manifest"):
        repo.register_run(changed,datasets,created_at=NOW)


def test_checkpoint_is_monotonic_and_bound_to_current_worker_epoch(tmp_path):
    datasets,dataset=_dataset(tmp_path)
    repo=TrainingRepository(tmp_path/"training.sqlite3")
    run=_manifest(dataset.digest)
    repo.register_run(run,datasets,created_at=NOW)
    repo.start(run.run_id)
    lease=repo.lease_worker(run.run_id,"worker-a",issued_at=NOW)
    first=_checkpoint(run,lease,10,"model-10")
    assert repo.checkpoint(first,lease)==first.digest
    with pytest.raises(TrainingStateError,match="strictly monotonic"):
        repo.checkpoint(_checkpoint(run,lease,10,"model-other"),lease)


def test_elastic_recovery_fences_stale_workers_and_resumes_from_checkpoint(tmp_path):
    datasets,dataset=_dataset(tmp_path)
    repo=TrainingRepository(tmp_path/"training.sqlite3")
    run=_manifest(dataset.digest)
    repo.register_run(run,datasets,created_at=NOW)
    repo.start(run.run_id)
    stale=repo.lease_worker(run.run_id,"worker-a",issued_at=NOW)
    checkpoint=_checkpoint(run,stale,20,"model-20")
    repo.checkpoint(checkpoint,stale)
    repo.fail(run.run_id)
    recovered=repo.recover(run.run_id)
    assert recovered.digest==checkpoint.digest
    assert repo.state(run.run_id)=="recovering"
    repo.start(run.run_id)
    with pytest.raises(TrainingStateError,match="stale worker epoch|not current"):
        repo.assert_worker_current(stale)
    fresh=repo.lease_worker(run.run_id,"worker-b",issued_at=NOW)
    assert fresh.epoch==stale.epoch+1
    next_checkpoint=_checkpoint(run,fresh,21,"model-21")
    assert repo.checkpoint(next_checkpoint,fresh)==next_checkpoint.digest


def test_nonfinite_training_telemetry_is_rejected(tmp_path):
    datasets,dataset=_dataset(tmp_path)
    repo=TrainingRepository(tmp_path/"training.sqlite3")
    run=_manifest(dataset.digest)
    repo.register_run(run,datasets,created_at=NOW)
    repo.start(run.run_id)
    with pytest.raises(ValueError,match="non-finite"):
        TrainingTelemetry(run.run_id,1,{"loss":math.nan},NOW.isoformat())


def test_completion_requires_checkpoint(tmp_path):
    datasets,dataset=_dataset(tmp_path)
    repo=TrainingRepository(tmp_path/"training.sqlite3")
    run=_manifest(dataset.digest)
    repo.register_run(run,datasets,created_at=NOW)
    repo.start(run.run_id)
    with pytest.raises(TrainingStateError,match="durable checkpoint"):
        repo.complete(run.run_id)

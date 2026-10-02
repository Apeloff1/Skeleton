from __future__ import annotations

from datetime import datetime, timezone
import socket

import pytest

from skeleton.data.native_pipeline import NativeDatasetRepository, QualityPolicy
from skeleton.learning.native_training import (
    NativeTrainingController,
    NativeTrainingRequest,
    SQLiteTrainingRunStore,
    TrainingCancelled,
    TrainingState,
    build_training_plan,
)


NOW=datetime(2026,10,2,6,20,tzinfo=timezone.utc)
SCHEMA={"type":"array","items":{"type":"object","properties":{"text":{"type":"string"}}}}


def _fixture(tmp_path):
    datasets=NativeDatasetRepository(tmp_path/"datasets.sqlite3",cas_root=tmp_path/"cas")
    version=datasets.commit(
        tenant_id="tenant-a",
        dataset_id="corpus",
        rows=[
            {"text":"local models learn from local evidence"},
            {"text":"native training preserves provenance"},
            {"text":"checkpoint recovery prevents silent loss"},
            {"text":"evaluation gates constrain promotion"},
        ],
        schema=SCHEMA,
        source_id="p3-t2-fixture",
        quality_policy=QualityPolicy(required_fields=("text",)),
        expected_version=0,
        now=NOW,
    )
    request=NativeTrainingRequest(
        tenant_id="tenant-a",
        run_id="run-001",
        dataset_id="corpus",
        dataset_version=1,
        dataset_manifest_digest=version.manifest_digest,
        text_field="text",
        model_id="native-p3-reference",
        code_revision="fixture-revision",
        seed=41,
        shard_count=3,
        hyperparameters={"order":2},
    )
    return datasets,version,request


def test_training_plan_is_deterministic_and_exact(tmp_path) -> None:
    datasets,version,request=_fixture(tmp_path)
    first=build_training_plan(request,version)
    second=build_training_plan(request,version)
    assert first==second
    assert first.shard_count==len(first.shards)
    covered=sorted(i for shard in first.shards for i in shard.row_indices)
    assert covered==[0,1,2,3]
    datasets.close()


def test_native_training_completes_without_provider_or_network(tmp_path,monkeypatch) -> None:
    datasets,_,request=_fixture(tmp_path)
    runs=SQLiteTrainingRunStore(tmp_path/"training.sqlite3")

    original_create_connection=socket.create_connection
    def blocked(*args,**kwargs):
        raise AssertionError("native training attempted network I/O")
    monkeypatch.setattr(socket,"create_connection",blocked)

    controller=NativeTrainingController(datasets,runs)
    result=controller.execute(
        request,
        rights_refs=("rights:fixture",),
        source_refs=("source:fixture",),
        now=NOW,
    )
    assert result.state is TrainingState.COMPLETED
    assert result.model_id=="native-p3-reference"
    assert result.model_digest is not None
    assert result.training_receipt_digest is not None
    assert result.artifact_cas_digest is not None
    assert datasets.cas.get(result.artifact_cas_digest)
    monkeypatch.setattr(socket,"create_connection",original_create_connection)
    runs.close(); datasets.close()


def test_completed_run_is_idempotent_across_controller_restart(tmp_path) -> None:
    datasets,_,request=_fixture(tmp_path)
    path=tmp_path/"training.sqlite3"
    first_store=SQLiteTrainingRunStore(path)
    first=NativeTrainingController(datasets,first_store).execute(
        request,
        rights_refs=("rights:fixture",),
        source_refs=("source:fixture",),
        now=NOW,
    )
    first_store.close()

    second_store=SQLiteTrainingRunStore(path)
    second=NativeTrainingController(datasets,second_store).execute(
        request,
        rights_refs=("rights:fixture",),
        source_refs=("source:fixture",),
        now=NOW,
    )
    assert second.model_digest==first.model_digest
    assert second.training_receipt_digest==first.training_receipt_digest
    assert second.artifact_cas_digest==first.artifact_cas_digest
    second_store.close(); datasets.close()


def test_prepared_run_can_resume_after_restart(tmp_path) -> None:
    datasets,_,request=_fixture(tmp_path)
    path=tmp_path/"training.sqlite3"
    first_store=SQLiteTrainingRunStore(path)
    plan=NativeTrainingController(datasets,first_store).prepare(request,now=NOW)
    assert first_store.row(request.run_id)["state"]=="prepared"
    first_store.close()

    second_store=SQLiteTrainingRunStore(path)
    result=NativeTrainingController(datasets,second_store).execute(
        request,
        rights_refs=("rights:fixture",),
        source_refs=("source:fixture",),
        now=NOW,
    )
    assert result.completed is True
    assert result.plan_digest==plan.digest
    second_store.close(); datasets.close()


def test_cancellation_is_durable_and_prevents_training(tmp_path) -> None:
    datasets,_,request=_fixture(tmp_path)
    store=SQLiteTrainingRunStore(tmp_path/"training.sqlite3")
    controller=NativeTrainingController(datasets,store)
    controller.prepare(request,now=NOW)
    store.request_cancel(request.run_id)
    with pytest.raises(TrainingCancelled):
        controller.execute(
            request,
            rights_refs=("rights:fixture",),
            source_refs=("source:fixture",),
            now=NOW,
        )
    assert TrainingState(store.row(request.run_id)["state"]) is TrainingState.CANCELLED
    assert store.result(request.run_id) is None
    store.close(); datasets.close()

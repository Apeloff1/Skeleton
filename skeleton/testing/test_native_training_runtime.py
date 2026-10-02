from __future__ import annotations

import socket

import pytest

from skeleton.ai.runtime.training import (
    ContentAddressedDatasetRegistry,
    DatasetManifest,
    DatasetRecord,
    DatasetRightsError,
    NativeTrainingCheckpoint,
    NativeTrainingConfig,
    NativeTrainingControlPlane,
    TrainingTopology,
)


def _dataset() -> DatasetManifest:
    return DatasetManifest(
        dataset_id="math-mini",
        version="1",
        records=(
            DatasetRecord("r1", "two plus two four", "fixture:r1", "CC0-1.0", "train_eval"),
            DatasetRecord("r2", "three plus three six", "fixture:r2", "CC0-1.0", "train_eval"),
            DatasetRecord("r3", "four plus four eight", "fixture:r3", "CC0-1.0", "train_eval"),
        ),
    )


def test_dataset_identity_is_content_addressed_and_immutable() -> None:
    registry=ContentAddressedDatasetRegistry()
    first=_dataset()
    digest=registry.register(first)
    assert registry.get(digest)==first
    changed=DatasetManifest(
        dataset_id="math-mini",
        version="1",
        records=(
            DatasetRecord("r1", "mutated", "fixture:r1", "CC0-1.0", "train_eval"),
        ),
    )
    with pytest.raises(ValueError,match="cannot be rebound"):
        registry.register(changed)


def test_training_admission_rejects_eval_only_or_restricted_records() -> None:
    control=NativeTrainingControlPlane()
    eval_only=DatasetManifest(
        dataset_id="eval-only",
        version="1",
        records=(DatasetRecord("r1","held out","fixture","CC0-1.0","eval_only"),),
    )
    with pytest.raises(DatasetRightsError):
        control.train(eval_only,NativeTrainingConfig(evaluation_floor=0.0))

    restricted=DatasetManifest(
        dataset_id="restricted",
        version="1",
        records=(DatasetRecord("r1","secret","fixture","private","train",classification="restricted"),),
    )
    with pytest.raises(DatasetRightsError):
        control.train(restricted,NativeTrainingConfig(evaluation_floor=0.0))


def test_native_training_is_deterministic_across_worker_counts() -> None:
    dataset=_dataset()
    config=NativeTrainingConfig(order=2,epochs=3,evaluation_floor=0.5)
    single=NativeTrainingControlPlane().train(
        dataset,config,topology=TrainingTopology(("w0",),generation=1)
    )
    multi=NativeTrainingControlPlane().train(
        dataset,config,topology=TrainingTopology(("w0","w1","w2"),generation=2)
    )
    assert single.status=="completed"
    assert multi.status=="completed"
    assert single.model is not None and multi.model is not None
    assert single.model.model_digest==multi.model.model_digest
    assert single.mbom is not None and multi.mbom is not None
    assert single.mbom.dataset_digest==dataset.digest
    assert multi.mbom.model_digest==single.model.model_digest


def test_checkpoint_resume_matches_uninterrupted_training() -> None:
    dataset=_dataset()
    config=NativeTrainingConfig(order=2,epochs=4,evaluation_floor=0.5)
    control=NativeTrainingControlPlane()
    partial=control.train(
        dataset,config,
        topology=TrainingTopology(("a","b"),generation=1),
        stop_after_work_items=5,
    )
    assert partial.status=="checkpointed"
    assert partial.checkpoint is not None
    encoded=partial.checkpoint.as_dict()
    restored=NativeTrainingCheckpoint.from_dict(encoded)
    resumed=control.train(
        dataset,config,
        topology=TrainingTopology(("a","b","c"),generation=2),
        checkpoint=restored,
    )
    full=NativeTrainingControlPlane().train(
        dataset,config,
        topology=TrainingTopology(("z",),generation=1),
    )
    assert resumed.model is not None and full.model is not None
    assert resumed.model.model_digest==full.model.model_digest
    assert resumed.mbom is not None and full.mbom is not None
    assert resumed.mbom.digest==full.mbom.digest


def test_evaluation_gate_fails_closed_on_unseen_holdout() -> None:
    train=_dataset()
    holdout=DatasetManifest(
        dataset_id="novel",
        version="1",
        records=(DatasetRecord("h1","xylophone quantum nebula","fixture:h1","CC0-1.0","train_eval"),),
    )
    with pytest.raises(RuntimeError,match="evaluation gate failed"):
        NativeTrainingControlPlane().train(
            train,
            NativeTrainingConfig(order=2,epochs=1,evaluation_floor=0.95),
            holdout=holdout,
        )


def test_native_training_performs_no_network_io(monkeypatch) -> None:
    original=socket.socket
    def guard(*args,**kwargs):
        family=args[0] if args else kwargs.get("family",socket.AF_INET)
        if family in {socket.AF_INET,socket.AF_INET6}:
            raise AssertionError("native training attempted network I/O")
        return original(*args,**kwargs)
    monkeypatch.setattr(socket,"socket",guard)
    result=NativeTrainingControlPlane().train(
        _dataset(),
        NativeTrainingConfig(order=2,epochs=2,evaluation_floor=0.5),
    )
    assert result.status=="completed"
    assert result.model is not None

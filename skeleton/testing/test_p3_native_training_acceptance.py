from __future__ import annotations

from skeleton.ai.runtime.training import (
    ContentAddressedDatasetRegistry,
    DataIngestionEngine,
    DatasetManifest,
    LicensePolicyRegistry,
    LineageGraph,
    ModelLifecycleRegistry,
    ModelLifecycleState,
    NativeTrainingCheckpoint,
    NativeTrainingConfig,
    NativeTrainingControlPlane,
    PreferencePair,
    PreferenceWeightedPostTrainer,
    TrainingTopology,
    VerifierProgram,
)
from skeleton.ai.runtime.training.data import LicensePolicy


def test_p3_t2_provider_independent_training_transaction() -> None:
    rights=LicensePolicyRegistry((
        LicensePolicy("CC0-1.0",True,True,("local-model-training",)),
    ))
    ingest=DataIngestionEngine(max_bytes=4096)
    records=[]
    receipts=[]
    for index,text in enumerate((
        "two plus two four",
        "three plus three six",
        "four plus four eight",
        "five plus five ten",
    )):
        record,receipt=ingest.ingest(
            record_id=f"r{index}",
            text=text,
            source_ref=f"fixture:{index}",
            license_id="CC0-1.0",
            usage_grant="train_eval",
        )
        assert record is not None and receipt.quarantined is False
        assert rights.evaluate(record).permitted is True
        records.append(record); receipts.append(receipt)

    dataset=DatasetManifest(dataset_id="p3-t2-acceptance",version="1",records=tuple(records))
    registry=ContentAddressedDatasetRegistry()
    assert registry.register(dataset)==dataset.digest
    assert registry.quality(dataset).passing

    lineage=LineageGraph()
    for receipt in receipts:
        lineage.add_node(receipt.content_digest)

    config=NativeTrainingConfig(
        order=2,epochs=4,model_id="p3-t2-local-base",evaluation_floor=0.6
    )
    control=NativeTrainingControlPlane(registry)
    partial=control.train(
        dataset,config,
        topology=TrainingTopology(("worker-a","worker-b"),generation=1),
        stop_after_work_items=7,
    )
    assert partial.status=="checkpointed" and partial.checkpoint is not None
    checkpoint=NativeTrainingCheckpoint.from_dict(partial.checkpoint.as_dict())
    base=control.train(
        dataset,config,
        topology=TrainingTopology(("worker-a","worker-b","worker-c"),generation=2),
        checkpoint=checkpoint,
    )
    assert base.status=="completed"
    assert base.model is not None and base.mbom is not None and base.evaluation is not None
    assert base.evaluation.passed

    preferences=(
        PreferencePair(
            "pref-safe",
            "two plus two",
            "four",
            "five",
            "fixture:preference",
        ),
    )
    post=PreferenceWeightedPostTrainer().train(
        dataset,
        preferences,
        NativeTrainingConfig(
            order=2,epochs=3,model_id="p3-t2-local-post",evaluation_floor=0.6
        ),
        chosen_weight=4,
    )
    assert post.status=="completed"
    assert post.model is not None and post.mbom is not None and post.evaluation is not None

    calibration=VerifierProgram("p3-t2-independent-verifier").calibrate((
        (0.98,True),(0.90,True),(0.76,True),(0.51,False),(0.20,False),(0.05,False),
    ))
    assert calibration.accuracy==1.0
    assert VerifierProgram.verify(0.90,calibration)
    assert not VerifierProgram.verify(0.20,calibration)

    lifecycle=ModelLifecycleRegistry()
    lifecycle.register_candidate(base.mbom)
    lifecycle.register_candidate(post.mbom)
    lifecycle.transition(
        base.model.model_digest,
        ModelLifecycleState.VALIDATED,
        evidence={"evaluation":base.evaluation.as_dict()},
        evaluation=base.evaluation,
    )
    lifecycle.transition(
        base.model.model_digest,
        ModelLifecycleState.ACTIVE,
        evidence={"release":"local-base"},
        evaluation=base.evaluation,
    )
    lifecycle.transition(
        post.model.model_digest,
        ModelLifecycleState.VALIDATED,
        evidence={"evaluation":post.evaluation.as_dict(),"verifier":calibration.calibration_digest},
        evaluation=post.evaluation,
    )
    migration=lifecycle.migration_decision(
        source_model_digest=base.model.model_digest,
        target_model_digest=post.model.model_digest,
        parity_score=0.95,
        required_score=0.90,
        evidence={
            "dataset":dataset.digest,
            "base_mbom":base.mbom.digest,
            "target_mbom":post.mbom.digest,
            "verifier":calibration.calibration_digest,
        },
    )
    assert migration.approved is True
    assert migration.rollback_model_digest==base.model.model_digest

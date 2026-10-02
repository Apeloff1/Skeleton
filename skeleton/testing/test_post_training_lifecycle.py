from __future__ import annotations

import pytest

from skeleton.ai.runtime.training import (
    CurriculumEngine,
    CurriculumStage,
    DatasetManifest,
    DatasetRecord,
    DeterministicRLEnvironment,
    ModelLifecycleRegistry,
    ModelLifecycleState,
    NativeTrainingConfig,
    NativeTrainingControlPlane,
    PreferencePair,
    PreferenceWeightedPostTrainer,
    TrainingTopology,
    VerifierProgram,
)
from skeleton.ai.runtime.training.post_training import RLTransition


def _dataset(name: str, text: str) -> DatasetManifest:
    return DatasetManifest(
        dataset_id=name,version="1",
        records=(
            DatasetRecord("r1",text,"fixture:r1","CC0-1.0","train_eval"),
            DatasetRecord("r2",text+" verified","fixture:r2","CC0-1.0","train_eval"),
        ),
    )


def test_preference_post_training_is_deterministic_and_lineage_bound() -> None:
    base=_dataset("base","answer safe")
    prefs=(PreferencePair("p1","question","answer preferred","answer unsafe","fixture:pref"),)
    trainer=PreferenceWeightedPostTrainer()
    generated=trainer.build_dataset(base,prefs,chosen_weight=3)
    synthetic=[r for r in generated.records if r.synthetic_parent_refs]
    assert len(synthetic)==1
    assert synthetic[0].synthetic_parent_refs==("preference:p1",)
    assert synthetic[0].text.count("answer preferred")==3
    config=NativeTrainingConfig(order=2,epochs=2,evaluation_floor=0.5)
    a=trainer.train(base,prefs,config,chosen_weight=3)
    b=trainer.train(base,prefs,config,chosen_weight=3)
    assert a.model is not None and b.model is not None
    assert a.model.model_digest==b.model.model_digest


def test_deterministic_rl_environment_resets_and_replays() -> None:
    env=DeterministicRLEnvironment(
        environment_id="two-step",
        initial_state="start",
        transitions=(
            RLTransition("start","inspect","ready",0.1),
            RLTransition("ready","finish","done",1.0,True),
        ),
    )
    first=env.rollout(("inspect","finish"))
    second=env.rollout(("inspect","finish"))
    assert first==second
    assert sum(step.reward for step in first)==pytest.approx(1.1)
    assert first[-1].terminal is True
    assert len(env.digest)==64


def test_curriculum_unlocks_only_contiguous_passing_stages() -> None:
    engine=CurriculumEngine((
        CurriculumStage("s1",0.7,"basic"),
        CurriculumStage("s2",0.8,"tool"),
        CurriculumStage("s3",0.9,"research"),
    ))
    assert engine.unlocked({"basic":0.9,"tool":0.79,"research":1.0})==("s1",)
    assert engine.next_stage({"basic":0.9,"tool":0.79}).stage_id=="s2"


def test_verifier_calibration_prefers_accuracy_then_low_false_positive_rate() -> None:
    calibration=VerifierProgram("quality-v1").calibrate((
        (0.95,True),(0.8,True),(0.55,True),(0.5,False),(0.2,False),(0.1,False),
    ))
    assert calibration.accuracy==1.0
    assert calibration.false_positive_rate==0.0
    assert VerifierProgram.verify(0.8,calibration)
    assert not VerifierProgram.verify(0.2,calibration)


def _trained(name: str, text: str):
    result=NativeTrainingControlPlane().train(
        _dataset(name,text),
        NativeTrainingConfig(model_id=name,order=2,epochs=2,evaluation_floor=0.5),
        topology=TrainingTopology(("w0","w1"),generation=1),
    )
    assert result.model is not None and result.mbom is not None and result.evaluation is not None
    return result


def test_model_lifecycle_and_migration_fail_closed() -> None:
    source=_trained("source","alpha beta gamma")
    target=_trained("target","alpha beta delta")
    registry=ModelLifecycleRegistry()
    registry.register_candidate(source.mbom)
    registry.register_candidate(target.mbom)

    registry.transition(source.model.model_digest,ModelLifecycleState.VALIDATED,evidence={"gate":"source"},evaluation=source.evaluation)
    registry.transition(source.model.model_digest,ModelLifecycleState.ACTIVE,evidence={"release":"r1"},evaluation=source.evaluation)
    registry.transition(target.model.model_digest,ModelLifecycleState.VALIDATED,evidence={"gate":"target"},evaluation=target.evaluation)

    denied=registry.migration_decision(
        source_model_digest=source.model.model_digest,
        target_model_digest=target.model.model_digest,
        parity_score=0.89,required_score=0.9,evidence={"suite":"parity-v1"},
    )
    assert denied.approved is False
    assert denied.rollback_model_digest==source.model.model_digest

    approved=registry.migration_decision(
        source_model_digest=source.model.model_digest,
        target_model_digest=target.model.model_digest,
        parity_score=0.95,required_score=0.9,evidence={"suite":"parity-v2"},
    )
    assert approved.approved is True

    with pytest.raises(ValueError,match="illegal"):
        registry.transition(source.model.model_digest,ModelLifecycleState.RETIRED,evidence={"skip":"bad"})


def test_activation_rejects_missing_evaluation() -> None:
    result=_trained("candidate","one two three")
    registry=ModelLifecycleRegistry(); registry.register_candidate(result.mbom)
    with pytest.raises(ValueError,match="requires passing"):
        registry.transition(result.model.model_digest,ModelLifecycleState.VALIDATED,evidence={"gate":"missing"})

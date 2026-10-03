from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.runtime.training import (
    CurriculumEngine,
    CurriculumStage,
    DeterministicRLEnvironment,
    PostTrainingExperiment,
    PostTrainingLedger,
    RLEnvironmentSpec,
)


def _digest(text:str)->str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_post_training_experiment_never_grants_production_authority(tmp_path):
    experiment=PostTrainingExperiment(
        experiment_id="post-001",
        base_candidate_digest=_digest("candidate"),
        dataset_digest=_digest("dataset"),
        objective="improve arithmetic reliability",
        algorithm="reinforcement-learning",
        configuration={"learning_rate":0.0001},
        evaluation_suite_digest=_digest("eval-suite"),
    )
    assert experiment.as_dict()["production_authority"] is False
    ledger=PostTrainingLedger(tmp_path/"post.sqlite3")
    assert ledger.register_experiment(experiment)==experiment.digest


def test_rl_environment_is_sandboxed_versioned_and_deterministic(tmp_path):
    spec=RLEnvironmentSpec(
        environment_id="bandit",
        version="1",
        state_schema_digest=_digest("state-schema"),
        action_schema_digest=_digest("action-schema"),
        reward_logic_digest=_digest("reward-v1"),
    )
    ledger=PostTrainingLedger(tmp_path/"post.sqlite3")
    ledger.register_environment(spec)

    first=DeterministicRLEnvironment(spec,rewards={"good":1.0,"bad":-1.0},terminal_actions=("good",))
    second=DeterministicRLEnvironment(spec,rewards={"good":1.0,"bad":-1.0},terminal_actions=("good",))
    assert first.reset(episode_id="episode-1",seed=7)==second.reset(episode_id="episode-1",seed=7)
    a=first.step("bad"); b=second.step("bad")
    assert a.as_dict()==b.as_dict()
    assert ledger.record_step(a)==a.digest
    terminal=first.step("good")
    assert terminal.terminal is True


def test_rl_environment_cannot_enable_external_side_effects():
    with pytest.raises(ValueError,match="external side effects"):
        RLEnvironmentSpec(
            environment_id="unsafe",
            version="1",
            state_schema_digest=_digest("state"),
            action_schema_digest=_digest("action"),
            reward_logic_digest=_digest("reward"),
            external_side_effects_allowed=True,
        )


def test_curriculum_enforces_prerequisites_and_metric_thresholds(tmp_path):
    engine=CurriculumEngine((
        CurriculumStage("foundation","basic arithmetic","foundation_accuracy",0.9),
        CurriculumStage("reasoning","multi-step arithmetic","reasoning_accuracy",0.8,("foundation",)),
    ))
    blocked=engine.decide("reasoning",metrics={"reasoning_accuracy":1.0},completed=())
    assert blocked.status=="blocked"

    hold=engine.decide("foundation",metrics={"foundation_accuracy":0.5},completed=())
    assert hold.status=="hold"

    advance=engine.decide("foundation",metrics={"foundation_accuracy":0.95},completed=())
    assert advance.status=="advance"

    reasoning=engine.decide(
        "reasoning",
        metrics={"reasoning_accuracy":0.85},
        completed=("foundation",),
    )
    assert reasoning.status=="advance"

    ledger=PostTrainingLedger(tmp_path/"post.sqlite3")
    assert ledger.record_curriculum(reasoning)==reasoning.digest


def test_curriculum_cycle_is_rejected():
    with pytest.raises(ValueError,match="cycle"):
        CurriculumEngine((
            CurriculumStage("a","a","a_metric",1.0,("b",)),
            CurriculumStage("b","b","b_metric",1.0,("a",)),
        ))


def test_environment_version_identity_detects_reward_logic_drift(tmp_path):
    ledger=PostTrainingLedger(tmp_path/"post.sqlite3")
    original=RLEnvironmentSpec(
        environment_id="env",
        version="1",
        state_schema_digest=_digest("state"),
        action_schema_digest=_digest("action"),
        reward_logic_digest=_digest("reward-v1"),
    )
    ledger.register_environment(original)
    drifted=RLEnvironmentSpec(
        environment_id="env",
        version="1",
        state_schema_digest=_digest("state"),
        action_schema_digest=_digest("action"),
        reward_logic_digest=_digest("reward-v2"),
    )
    with pytest.raises(ValueError,match="immutable"):
        ledger.register_environment(drifted)

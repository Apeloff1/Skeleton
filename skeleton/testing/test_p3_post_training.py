from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.runtime.training import (
    CurriculumDecision,
    CurriculumEngine,
    CurriculumStage,
    DeterministicRLEnvironment,
    PostTrainingExperiment,
    PostTrainingLedger,
    RLEnvironmentSpec,
    RLStepReceipt,
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

def test_rl_environment_requires_reset_after_terminal_action():
    spec=RLEnvironmentSpec(
        environment_id="terminal-env",
        version="1",
        state_schema_digest=_digest("terminal-state"),
        action_schema_digest=_digest("terminal-action"),
        reward_logic_digest=_digest("terminal-reward"),
    )
    env=DeterministicRLEnvironment(
        spec,
        rewards={"continue":0.0,"finish":1.0},
        terminal_actions=("finish",),
    )
    env.reset(episode_id="episode-terminal",seed=3)
    terminal=env.step("finish")
    assert terminal.terminal is True

    with pytest.raises(RuntimeError,match="episode is terminal"):
        env.step("continue")

    env.reset(episode_id="episode-new",seed=3)
    assert env.step("continue").step==1


def test_rl_ledger_rejects_orphan_and_forked_trajectory_steps(tmp_path):
    spec=RLEnvironmentSpec(
        environment_id="chain-env",
        version="1",
        state_schema_digest=_digest("chain-state"),
        action_schema_digest=_digest("chain-action"),
        reward_logic_digest=_digest("chain-reward"),
    )
    ledger=PostTrainingLedger(tmp_path/"chain.sqlite3")
    ledger.register_environment(spec)
    env=DeterministicRLEnvironment(
        spec,
        rewards={"continue":0.0},
    )
    env.reset(episode_id="episode-chain",seed=5)
    first=env.step("continue")
    ledger.record_step(first)

    orphan=RLStepReceipt(
        environment_digest=spec.digest,
        episode_id="episode-chain",
        step=3,
        action="continue",
        reward=0.0,
        terminal=False,
        state_digest=first.next_state_digest,
        next_state_digest=_digest("orphan-next"),
    )
    with pytest.raises(ValueError,match="step must be contiguous"):
        ledger.record_step(orphan)

    fork=RLStepReceipt(
        environment_digest=spec.digest,
        episode_id="episode-chain",
        step=2,
        action="continue",
        reward=0.0,
        terminal=False,
        state_digest=_digest("wrong-parent"),
        next_state_digest=_digest("fork-next"),
    )
    with pytest.raises(ValueError,match="state chain"):
        ledger.record_step(fork)


def test_rl_ledger_rejects_evidence_after_terminal_receipt(tmp_path):
    spec=RLEnvironmentSpec(
        environment_id="ledger-terminal",
        version="1",
        state_schema_digest=_digest("ledger-terminal-state"),
        action_schema_digest=_digest("ledger-terminal-action"),
        reward_logic_digest=_digest("ledger-terminal-reward"),
    )
    ledger=PostTrainingLedger(tmp_path/"terminal.sqlite3")
    ledger.register_environment(spec)
    env=DeterministicRLEnvironment(
        spec,
        rewards={"finish":1.0},
        terminal_actions=("finish",),
    )
    env.reset(episode_id="episode-ledger-terminal",seed=11)
    terminal=env.step("finish")
    ledger.record_step(terminal)

    after=RLStepReceipt(
        environment_digest=spec.digest,
        episode_id=terminal.episode_id,
        step=terminal.step+1,
        action="finish",
        reward=1.0,
        terminal=True,
        state_digest=terminal.next_state_digest,
        next_state_digest=_digest("after-terminal"),
    )
    with pytest.raises(ValueError,match="already terminal"):
        ledger.record_step(after)

def test_rl_receipt_rejects_boolean_or_zero_step():
    base=dict(
        environment_digest=_digest("env"),
        episode_id="episode",
        action="act",
        reward=1.0,
        terminal=False,
        state_digest=_digest("state"),
        next_state_digest=_digest("next"),
    )
    with pytest.raises(ValueError,match="positive integer"):
        RLStepReceipt(step=True,**base)
    with pytest.raises(ValueError,match="positive integer"):
        RLStepReceipt(step=0,**base)


def test_rl_receipt_requires_boolean_terminal_flag():
    with pytest.raises(ValueError,match="terminal flag"):
        RLStepReceipt(
            environment_digest=_digest("env"),
            episode_id="episode",
            step=1,
            action="act",
            reward=1.0,
            terminal="yes",
            state_digest=_digest("state"),
            next_state_digest=_digest("next"),
        )


def test_rl_ledger_detects_tampered_environment_payload(tmp_path):
    spec=RLEnvironmentSpec(
        environment_id="tamper-env",
        version="1",
        state_schema_digest=_digest("state"),
        action_schema_digest=_digest("action"),
        reward_logic_digest=_digest("reward"),
    )
    ledger=PostTrainingLedger(tmp_path/"tamper-env.sqlite3")
    ledger.register_environment(spec)
    ledger._db.execute(
        "UPDATE environment SET payload=? WHERE environment_digest=?",
        ('{"environment_id":"tampered","version":"1"}',spec.digest),
    )
    ledger._db.commit()
    env=DeterministicRLEnvironment(spec,rewards={"go":1.0})
    env.reset(episode_id="episode",seed=1)

    with pytest.raises(ValueError,match="environment identity mismatch"):
        ledger.record_step(env.step("go"))


def test_rl_ledger_detects_tampered_prior_receipt(tmp_path):
    spec=RLEnvironmentSpec(
        environment_id="tamper-step",
        version="1",
        state_schema_digest=_digest("state-step"),
        action_schema_digest=_digest("action-step"),
        reward_logic_digest=_digest("reward-step"),
    )
    ledger=PostTrainingLedger(tmp_path/"tamper-step.sqlite3")
    ledger.register_environment(spec)
    env=DeterministicRLEnvironment(spec,rewards={"go":1.0})
    env.reset(episode_id="episode",seed=2)
    first=env.step("go")
    ledger.record_step(first)
    ledger._db.execute(
        "UPDATE rl_step SET payload=? WHERE receipt_digest=?",
        ('{"episode_id":"episode","step":1}',first.digest),
    )
    ledger._db.commit()

    with pytest.raises(ValueError,match="receipt digest mismatch"):
        ledger.record_step(env.step("go"))


def test_curriculum_decision_rejects_forged_metric_shapes():
    with pytest.raises(ValueError,match="advance decision requires metric"):
        CurriculumDecision(
            stage_id="foundation",
            status="advance",
            metric_value=None,
            reason="claimed pass",
            completed_before=(),
        )
    with pytest.raises(ValueError,match="blocked decision cannot carry metric"):
        CurriculumDecision(
            stage_id="reasoning",
            status="blocked",
            metric_value=1.0,
            reason="missing prerequisite",
            completed_before=(),
        )


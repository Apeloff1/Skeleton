from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.runtime.learning_foundation.learning import (
    CurriculumStage,
    LearningProgram,
    LearningProgramError,
    ReinforcementEnvironment,
    VerifierCandidate,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _program() -> tuple[LearningProgram, ReinforcementEnvironment]:
    program = LearningProgram()
    environment = ReinforcementEnvironment(
        environment_id="safe-code-repair-v1",
        observation_schema_digest=_sha("observations-v1"),
        action_schema_digest=_sha("actions-v1"),
        reward_min=-1.0,
        reward_max=1.0,
        max_steps=4,
        safety_constraint_refs=("policy:no-network", "policy:workspace-boundary"),
    )
    program.register_environment(environment)
    return program, environment


def test_episode_enforces_reward_and_step_bounds() -> None:
    program, environment = _program()
    receipt = program.record_episode(
        episode_id="ep-1",
        environment_id=environment.environment_id,
        policy_digest=_sha("policy-v1"),
        seed=7,
        rewards=(0.25, 0.75),
        terminated=True,
        observations_digest=_sha("obs-1"),
        actions_digest=_sha("actions-1"),
    )
    assert receipt.total_reward == 1.0
    assert receipt.failed is False

    with pytest.raises(LearningProgramError, match="reward"):
        program.record_episode(
            episode_id="ep-bad",
            environment_id=environment.environment_id,
            policy_digest=_sha("policy-v1"),
            seed=8,
            rewards=(2.0,),
            terminated=True,
            observations_digest=_sha("obs-bad"),
            actions_digest=_sha("actions-bad"),
        )


def test_curriculum_progression_requires_episode_count_reward_and_safety() -> None:
    program, environment = _program()
    ids = []
    for index, rewards in enumerate(((0.5, 0.5), (0.4, 0.6)), start=1):
        receipt = program.record_episode(
            episode_id=f"ep-{index}",
            environment_id=environment.environment_id,
            policy_digest=_sha("policy-v1"),
            seed=index,
            rewards=rewards,
            terminated=True,
            observations_digest=_sha(f"obs-{index}"),
            actions_digest=_sha(f"act-{index}"),
        )
        ids.append(receipt.episode_id)

    stage = CurriculumStage(
        stage_id="stage-1",
        environment_id=environment.environment_id,
        minimum_mean_reward=0.9,
        required_episodes=2,
        maximum_failure_rate=0.0,
    )
    decision = program.evaluate_stage(stage, episode_ids=ids)
    assert decision.passed is True
    assert decision.failure_rate == 0.0

    with pytest.raises(LearningProgramError, match="required episode"):
        program.evaluate_stage(stage, episode_ids=ids[:1])


def test_safety_violation_blocks_curriculum_gate() -> None:
    program, environment = _program()
    safe = program.record_episode(
        episode_id="safe",
        environment_id=environment.environment_id,
        policy_digest=_sha("policy-v1"),
        seed=1,
        rewards=(1.0,),
        terminated=True,
        observations_digest=_sha("obs-safe"),
        actions_digest=_sha("act-safe"),
    )
    bad = program.record_episode(
        episode_id="bad",
        environment_id=environment.environment_id,
        policy_digest=_sha("policy-v1"),
        seed=2,
        rewards=(1.0,),
        terminated=True,
        violation_refs=("violation:workspace-escape",),
        observations_digest=_sha("obs-bad"),
        actions_digest=_sha("act-bad"),
    )
    stage = CurriculumStage(
        stage_id="stage-safe",
        environment_id=environment.environment_id,
        minimum_mean_reward=0.5,
        required_episodes=2,
        maximum_failure_rate=0.0,
    )
    decision = program.evaluate_stage(stage, episode_ids=(safe.episode_id, bad.episode_id))
    assert decision.passed is False
    assert decision.failure_rate == 0.5


def test_verifier_model_program_requires_independent_evidence() -> None:
    program, environment = _program()
    episode = program.record_episode(
        episode_id="ep",
        environment_id=environment.environment_id,
        policy_digest=_sha("policy"),
        seed=1,
        rewards=(1.0,),
        terminated=True,
        observations_digest=_sha("obs"),
        actions_digest=_sha("act"),
    )
    stage = CurriculumStage(
        stage_id="stage",
        environment_id=environment.environment_id,
        minimum_mean_reward=1.0,
        required_episodes=1,
        maximum_failure_rate=0.0,
    )
    curriculum = program.evaluate_stage(stage, episode_ids=(episode.episode_id,))
    candidate = VerifierCandidate(
        candidate_id="verifier-candidate-1",
        model_digest=_sha("model"),
        training_receipt_digest=_sha("training-receipt"),
        benchmark_refs=("benchmark:heldout-v1",),
        intended_claims=("claim:tool-output-validity",),
    )

    with pytest.raises(LearningProgramError, match="independent verifier"):
        program.evaluate_verifier_candidate(
            candidate,
            verifier_id="trainer-v1",
            trainer_id="trainer-v1",
            evaluation_refs=("eval:a", "eval:b"),
            curriculum_decision_refs=(curriculum.decision_digest,),
        )

    decision = program.evaluate_verifier_candidate(
        candidate,
        verifier_id="independent-verifier-v1",
        trainer_id="trainer-v1",
        evaluation_refs=("eval:a", "eval:b"),
        curriculum_decision_refs=(curriculum.decision_digest,),
    )
    assert decision.passed is True
    assert decision.candidate_digest == candidate.digest

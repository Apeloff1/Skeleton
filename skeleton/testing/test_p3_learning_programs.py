from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace

import pytest

from skeleton.ai.runtime.learning_foundation.learning import (
    CurriculumStage,
    LearningProgram,
    LearningProgramError,
    ReinforcementEnvironment,
    VerifierCandidate,
)
from skeleton.ai.runtime.training.evaluation import EvaluationCase, EvaluationSuite
from skeleton.learning.model_program import (
    ModelDevelopmentRegistry,
    ReferenceNGramTrainer,
    TrainingDataset,
    TrainingSpec,
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


def _trained_candidate():
    corpus = ("hello local evidence world",)
    dataset = TrainingDataset.from_corpus(
        dataset_id="verifier-data",
        corpus=corpus,
        source_refs=("source:fixture",),
        rights_refs=("rights:fixture",),
    )
    registry = ModelDevelopmentRegistry()
    registry.register_dataset(dataset)
    artifact, receipt = registry.train(
        TrainingSpec(
            run_id="verifier-training",
            model_id="verifier-local-model",
            dataset_ids=(dataset.dataset_id,),
            trainer_id=ReferenceNGramTrainer.trainer_id,
            code_revision="verifier-evidence-fixture",
            seed=1,
            hyperparameters={"order": 2},
        ),
        corpora={dataset.dataset_id: corpus},
        trainer=ReferenceNGramTrainer(),
    )
    candidate = VerifierCandidate(
        candidate_id="verifier-candidate-1",
        model_digest=artifact.model_digest,
        training_receipt_digest=receipt.digest,
        benchmark_refs=("benchmark:heldout-v1",),
        intended_claims=("claim:tool-output-validity",),
    )
    return candidate, receipt, artifact.load_reference_model()


def _episode(program, environment, policy_digest, *, episode_id="ep", rewards=(1.0,), terminated=True):
    return program.record_episode(
        episode_id=episode_id,
        environment_id=environment.environment_id,
        policy_digest=policy_digest,
        seed=1,
        rewards=rewards,
        terminated=terminated,
        observations_digest=_sha(f"obs:{episode_id}"),
        actions_digest=_sha(f"act:{episode_id}"),
    )


def _stage(program, environment, episode, *, minimum_reward=1.0):
    return program.evaluate_stage(
        CurriculumStage(
            stage_id="stage",
            environment_id=environment.environment_id,
            minimum_mean_reward=minimum_reward,
            required_episodes=1,
            maximum_failure_rate=0.0,
        ),
        episode_ids=(episode.episode_id,),
    )


def _evaluations(program, candidate, receipt, model, *, failing=False):
    evidence = []
    for index, prompt in enumerate(("hello", "hello local")):
        suite = EvaluationSuite(
            suite_id=f"heldout:{index}",
            version="1",
            population="heldout",
            contamination_fingerprint=_sha(f"heldout:{index}"),
            cases=(
                EvaluationCase(
                    case_id=f"case:{index}",
                    prompt=prompt,
                    expected_substring="missing-output" if failing else "evidence",
                    max_output_tokens=8,
                ),
            ),
        )
        evidence.append(
            asyncio.run(
                program.evaluate_benchmark(
                    candidate,
                    model=model,
                    training_receipt=receipt,
                    benchmark_ref=candidate.benchmark_refs[0],
                    suite=suite,
                    verifier_id="independent-benchmark-verifier",
                    seed=index,
                )
            )
        )
    return tuple(item.digest for item in evidence)


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
    candidate, receipt, model = _trained_candidate()
    episode = _episode(program, environment, candidate.model_digest)
    curriculum = _stage(program, environment, episode)
    refs = _evaluations(program, candidate, receipt, model)

    with pytest.raises(LearningProgramError, match="independent verifier"):
        program.evaluate_verifier_candidate(
            candidate,
            verifier_id=receipt.trainer_id,
            trainer_id=receipt.trainer_id,
            evaluation_refs=refs,
            curriculum_decision_refs=(curriculum.decision_digest,),
        )

    decision = program.evaluate_verifier_candidate(
        candidate,
        verifier_id="independent-verifier-v1",
        trainer_id=receipt.trainer_id,
        evaluation_refs=refs,
        curriculum_decision_refs=(curriculum.decision_digest,),
    )
    assert decision.passed is True
    assert decision.candidate_digest == candidate.digest
    assert decision.production_promotion_authorized is False


def test_curriculum_cannot_combine_different_policy_models() -> None:
    program, environment = _program()
    first = _episode(program, environment, _sha("strong-model"), episode_id="strong")
    second = _episode(program, environment, _sha("weak-model"), episode_id="weak")
    stage = CurriculumStage("mixed", environment.environment_id, 1.0, 2, 0.0)
    with pytest.raises(LearningProgramError, match="one exact policy"):
        program.evaluate_stage(stage, episode_ids=(first.episode_id, second.episode_id))


def test_curriculum_cannot_count_same_episode_twice() -> None:
    program, environment = _program()
    episode = _episode(program, environment, _sha("policy"))
    stage = CurriculumStage("duplicates", environment.environment_id, 1.0, 2, 0.0)
    with pytest.raises(LearningProgramError, match="duplicate"):
        program.evaluate_stage(stage, episode_ids=(episode.episode_id, episode.episode_id))


def test_curriculum_digest_binds_thresholds_and_episode_trace() -> None:
    program, environment = _program()
    episode = _episode(program, environment, _sha("policy"))
    easier = _stage(program, environment, episode, minimum_reward=0.5)
    harder = _stage(program, environment, episode, minimum_reward=2.0)
    assert easier.passed is True and harder.passed is False
    assert easier.stage_digest != harder.stage_digest
    assert easier.decision_digest != harder.decision_digest
    assert easier.episode_trace_digests == (episode.trace_digest,)


@pytest.mark.parametrize("value", (True, "1", float("nan"), float("inf"), -float("inf")))
def test_episode_rewards_reject_coercion_and_nonfinite_values(value) -> None:
    program, environment = _program()
    with pytest.raises(LearningProgramError, match="numeric|finite"):
        _episode(program, environment, _sha("policy"), rewards=(value,))
    assert program._episodes == {}


@pytest.mark.parametrize("terminated", ("false", 1, None))
def test_episode_completion_requires_boolean(terminated) -> None:
    program, environment = _program()
    with pytest.raises(LearningProgramError, match="terminated must be boolean"):
        _episode(program, environment, _sha("policy"), terminated=terminated)


@pytest.mark.parametrize("value", (True, float("nan"), float("inf")))
def test_reward_and_curriculum_bounds_are_finite_numbers(value) -> None:
    _, environment = _program()
    with pytest.raises(LearningProgramError, match="numeric|finite"):
        replace(environment, reward_min=value)
    with pytest.raises(LearningProgramError, match="numeric|finite"):
        CurriculumStage("stage", environment.environment_id, value, 1, 0.0)
    with pytest.raises(LearningProgramError, match="numeric|finite"):
        CurriculumStage("stage", environment.environment_id, 1.0, 1, value)


def test_tampered_episode_receipt_cannot_supply_curriculum_evidence() -> None:
    program, environment = _program()
    episode = _episode(program, environment, _sha("policy"))
    program._episodes[episode.episode_id] = replace(episode, rewards=(0.5,))
    with pytest.raises(LearningProgramError, match="episode receipt integrity"):
        _stage(program, environment, episode)


def test_forged_curriculum_success_cannot_qualify_verifier() -> None:
    program, environment = _program()
    candidate, receipt, model = _trained_candidate()
    episode = _episode(program, environment, candidate.model_digest, rewards=(-1.0,))
    curriculum = _stage(program, environment, episode)
    program._curriculum_decisions[curriculum.decision_digest] = replace(curriculum, passed=True)
    refs = _evaluations(program, candidate, receipt, model)
    with pytest.raises(LearningProgramError, match="curriculum decision integrity"):
        program.evaluate_verifier_candidate(
            candidate,
            verifier_id="independent-final-verifier",
            trainer_id=receipt.trainer_id,
            evaluation_refs=refs,
            curriculum_decision_refs=(curriculum.decision_digest,),
        )


def test_other_policy_curriculum_cannot_qualify_candidate() -> None:
    program, environment = _program()
    candidate, receipt, model = _trained_candidate()
    episode = _episode(program, environment, _sha("another-model"))
    curriculum = _stage(program, environment, episode)
    refs = _evaluations(program, candidate, receipt, model)
    with pytest.raises(LearningProgramError, match="does not match candidate"):
        program.evaluate_verifier_candidate(
            candidate,
            verifier_id="independent-final-verifier",
            trainer_id=receipt.trainer_id,
            evaluation_refs=refs,
            curriculum_decision_refs=(curriculum.decision_digest,),
        )


def test_unresolved_evaluation_strings_cannot_qualify_candidate() -> None:
    program, environment = _program()
    candidate, receipt, _ = _trained_candidate()
    episode = _episode(program, environment, candidate.model_digest)
    curriculum = _stage(program, environment, episode)
    with pytest.raises(LearningProgramError, match="unknown executable evaluation"):
        program.evaluate_verifier_candidate(
            candidate,
            verifier_id="independent-final-verifier",
            trainer_id=receipt.trainer_id,
            evaluation_refs=("eval:caller-says-passed", "eval:another-claim"),
            curriculum_decision_refs=(curriculum.decision_digest,),
        )


def test_failed_executable_benchmark_blocks_candidate_with_passing_curriculum() -> None:
    program, environment = _program()
    candidate, receipt, model = _trained_candidate()
    episode = _episode(program, environment, candidate.model_digest)
    curriculum = _stage(program, environment, episode)
    refs = _evaluations(program, candidate, receipt, model, failing=True)
    decision = program.evaluate_verifier_candidate(
        candidate,
        verifier_id="independent-final-verifier",
        trainer_id=receipt.trainer_id,
        evaluation_refs=refs,
        curriculum_decision_refs=(curriculum.decision_digest,),
    )
    assert decision.passed is False


def test_benchmark_rejects_different_candidate_model_and_trainer_self_evaluation() -> None:
    program, _ = _program()
    candidate, receipt, model = _trained_candidate()
    suite = EvaluationSuite(
        "heldout", "1", (EvaluationCase("case", "hello", "evidence"),), "heldout", _sha("heldout")
    )
    arguments = {
        "model": model,
        "training_receipt": receipt,
        "benchmark_ref": candidate.benchmark_refs[0],
        "suite": suite,
    }
    with pytest.raises(LearningProgramError, match="identity mismatch"):
        asyncio.run(
            program.evaluate_benchmark(
                replace(candidate, model_digest=_sha("other")), verifier_id="independent", **arguments
            )
        )
    with pytest.raises(LearningProgramError, match="independent verifier"):
        asyncio.run(program.evaluate_benchmark(candidate, verifier_id=receipt.trainer_id, **arguments))


def test_measured_evaluation_receipt_cannot_be_replaced_by_success_flag() -> None:
    program, environment = _program()
    candidate, receipt, model = _trained_candidate()
    episode = _episode(program, environment, candidate.model_digest)
    curriculum = _stage(program, environment, episode)
    refs = _evaluations(program, candidate, receipt, model, failing=True)
    issued, suite, result = program._evaluations[refs[0]]
    program._evaluations[refs[0]] = (replace(issued, passed_cases=issued.total_cases), suite, result)
    with pytest.raises(LearningProgramError, match="evaluation receipt integrity"):
        program.evaluate_verifier_candidate(
            candidate,
            verifier_id="independent-final-verifier",
            trainer_id=receipt.trainer_id,
            evaluation_refs=refs,
            curriculum_decision_refs=(curriculum.decision_digest,),
        )


def test_measured_output_mutation_invalidates_evaluation_receipt() -> None:
    program, environment = _program()
    candidate, receipt, model = _trained_candidate()
    episode = _episode(program, environment, candidate.model_digest)
    curriculum = _stage(program, environment, episode)
    refs = _evaluations(program, candidate, receipt, model)
    _, _, result = program._evaluations[refs[0]]
    result.outputs["case:0"] = "caller replaced actual model output"
    with pytest.raises(LearningProgramError, match="classification mismatch|receipt integrity"):
        program.evaluate_verifier_candidate(
            candidate,
            verifier_id="independent-final-verifier",
            trainer_id=receipt.trainer_id,
            evaluation_refs=refs,
            curriculum_decision_refs=(curriculum.decision_digest,),
        )


def test_changing_trainer_identity_cannot_bypass_independence() -> None:
    program, environment = _program()
    candidate, receipt, model = _trained_candidate()
    episode = _episode(program, environment, candidate.model_digest)
    curriculum = _stage(program, environment, episode)
    refs = _evaluations(program, candidate, receipt, model)
    with pytest.raises(LearningProgramError, match="verifier/trainer identity mismatch"):
        program.evaluate_verifier_candidate(
            candidate,
            verifier_id=receipt.trainer_id,
            trainer_id="caller-invented-other-trainer",
            evaluation_refs=refs,
            curriculum_decision_refs=(curriculum.decision_digest,),
        )


def test_another_candidate_cannot_reuse_issued_benchmark_receipts() -> None:
    program, environment = _program()
    candidate, receipt, model = _trained_candidate()
    episode = _episode(program, environment, candidate.model_digest)
    curriculum = _stage(program, environment, episode)
    refs = _evaluations(program, candidate, receipt, model)
    with pytest.raises(LearningProgramError, match="evaluation receipt integrity"):
        program.evaluate_verifier_candidate(
            replace(candidate, candidate_id="other-candidate"),
            verifier_id="independent-final-verifier",
            trainer_id=receipt.trainer_id,
            evaluation_refs=refs,
            curriculum_decision_refs=(curriculum.decision_digest,),
        )


def test_environment_mutation_fails_before_episode_commit() -> None:
    program, environment = _program()
    object.__setattr__(environment, "reward_max", 99.0)
    with pytest.raises(LearningProgramError, match="environment receipt integrity"):
        _episode(program, environment, _sha("policy"), rewards=(99.0,))
    assert program._episodes == {}
    with pytest.raises(LearningProgramError, match="environment identity conflict"):
        program.register_environment(environment)

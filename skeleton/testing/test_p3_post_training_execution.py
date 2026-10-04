import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from skeleton.ai.runtime.inference import ReferenceNGramModel
from skeleton.ai.runtime.training.evaluation import EvaluationCase, EvaluationSuite
from skeleton.ai.runtime.training.learning_pipeline import (
    LocalPostTrainingPolicy,
    PostTrainingExecutionError,
    PostTrainingExecutionSpec,
    PostTrainingRunner,
)
from skeleton.ai.runtime.training.post_training import (
    CurriculumEngine,
    CurriculumStage,
    DeterministicRLEnvironment,
    PostTrainingExperiment,
    PostTrainingLedger,
    RLEnvironmentSpec,
)


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _policy(observation):
    return "wait" if observation.step == 1 else "finish"


def _fixture(
    tmp_path, *, run_id="execution", callback=_policy, max_steps=8, max_episodes=4, max_episode_steps=4
):
    model = ReferenceNGramModel.train(("two plus two four",) * 3, model_id="post-training-fixture")
    suite = EvaluationSuite(
        "local-math",
        "1",
        (EvaluationCase("sum", "two plus two", "four", 3),),
        "heldout",
        _sha("held-out-population"),
    )
    environment = DeterministicRLEnvironment(
        RLEnvironmentSpec("bounded-reward", "1", _sha("state"), _sha("action"), _sha("reward-v1")),
        rewards={"wait": 1.0, "finish": 2.0},
        terminal_actions=("finish",),
    )
    policy = LocalPostTrainingPolicy("local-policy", "1", model.model_digest, "policy-revision", callback)
    curriculum = CurriculumEngine(
        (
            CurriculumStage("reward", "bounded reward", "mean_reward", 3.0),
            CurriculumStage("terminal", "terminal episode", "terminal_rate", 1.0, ("reward",)),
        )
    )
    experiment = PostTrainingExperiment(
        "post-experiment",
        model.model_digest,
        _sha("governed-dataset"),
        "bounded policy qualification",
        "deterministic-local",
        {},
        suite.digest,
    )
    spec = PostTrainingExecutionSpec(
        run_id,
        experiment.digest,
        policy.digest,
        model.model_digest,
        PostTrainingExecutionSpec.curriculum_digest_for(curriculum),
        suite.digest,
        "trainer",
        max_steps,
        max_episodes,
        max_episode_steps,
    )
    ledger = PostTrainingLedger(tmp_path / "post.sqlite3")
    runner = PostTrainingRunner(ledger)
    binding = {
        "experiment": experiment,
        "environment": environment,
        "policy": policy,
        "curriculum": curriculum,
    }
    runner.bind_execution(spec, **binding)
    return ledger, runner, spec, binding, model, suite


def _curriculum(runner, spec, binding, episode):
    first = runner.evaluate_stage(
        spec.run_id,
        curriculum=binding["curriculum"],
        stage_id="reward",
        episode_refs=(episode.receipt_digest,),
    )
    second = runner.evaluate_stage(
        spec.run_id,
        curriculum=binding["curriculum"],
        stage_id="terminal",
        episode_refs=(episode.receipt_digest,),
    )
    return first, second


@pytest.mark.asyncio
async def test_executed_episode_curriculum_and_heldout_qualification_survive_restart(tmp_path):
    ledger, runner, spec, binding, model, suite = _fixture(tmp_path)
    episode = runner.run_episode(spec.run_id, episode_id="episode-a", seed=17)
    assert episode.steps == 2 and episode.total_reward == 3 and episode.terminal
    assert ledger._db.execute("SELECT COUNT(*) FROM rl_step").fetchone()[0] == 2
    stages = _curriculum(runner, spec, binding, episode)
    assert [item.decision.status for item in stages] == ["advance", "advance"]
    evaluation = await runner.evaluate_candidate(
        spec.run_id, model=model, suite=suite, verifier_id="independent"
    )
    qualified = runner.qualify_candidate(
        spec.run_id,
        curriculum_refs=tuple(item.receipt_digest for item in stages),
        evaluation_ref=evaluation.receipt_digest,
        verifier_id="qualification-verifier",
    )
    assert qualified.status == "qualified_candidate"
    assert qualified.production_promotion_authorized is False
    ledger.close()
    reopened = PostTrainingLedger(tmp_path / "post.sqlite3")
    resumed = PostTrainingRunner(reopened)
    replay = resumed.qualify_candidate(
        spec.run_id,
        curriculum_refs=qualified.curriculum_refs,
        evaluation_ref=evaluation.receipt_digest,
        verifier_id="qualification-verifier",
    )
    assert replay == qualified
    assert resumed.status(spec.run_id)["steps"] == 2


@pytest.mark.asyncio
async def test_actual_local_model_policy_drives_runtime_evidence_and_qualification(tmp_path):
    model = ReferenceNGramModel.train(("two plus two four",) * 3, model_id="post-training-fixture")

    def local_model_policy(observation):
        # Imports are fixed policy code. The callback receives only its immutable
        # observation; its captured model's actual digest is part of policy identity.
        import threading

        from skeleton.ai.runtime.inference import LocalInferenceRequest

        output = model.infer(
            LocalInferenceRequest(prompt="two plus two", max_output_tokens=3, seed=observation.seed),
            threading.Event(),
        ).text
        if "four" not in output:
            return "invalid-model-action"
        return "wait" if observation.step == 1 else "finish"

    ledger, runner, spec, binding, evaluated_model, suite = _fixture(tmp_path, callback=local_model_policy)
    assert evaluated_model.model_digest == model.model_digest == spec.model_digest
    episode = runner.run_episode(spec.run_id, episode_id="actual-model-policy", seed=31)
    assert episode.steps == 2 and episode.total_reward == 3 and episode.terminal
    stages = _curriculum(runner, spec, binding, episode)
    evaluation = await runner.evaluate_candidate(
        spec.run_id, model=evaluated_model, suite=suite, verifier_id="independent-model-policy-verifier"
    )
    qualified = runner.qualify_candidate(
        spec.run_id,
        curriculum_refs=tuple(item.receipt_digest for item in stages),
        evaluation_ref=evaluation.receipt_digest,
        verifier_id="independent-policy-qualification",
    )
    assert qualified.status == "qualified_candidate"
    assert qualified.model_digest == model.model_digest
    assert qualified.policy_digest == binding["policy"].digest
    ledger.close()


def test_restart_restores_environment_without_replaying_committed_policy_calls(tmp_path, monkeypatch):
    calls = []
    original = DeterministicRLEnvironment.step

    def interrupted_transition(environment, action):
        calls.append(environment._step + 1)
        if environment._step + 1 == 2 and len(calls) == 2:
            raise KeyboardInterrupt("simulated process loss")
        return original(environment, action)

    monkeypatch.setattr(DeterministicRLEnvironment, "step", interrupted_transition)
    ledger, runner, spec, binding, _, _ = _fixture(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        runner.run_episode(spec.run_id, episode_id="resumable", seed=7)
    assert runner.status(spec.run_id)["steps"] == 1
    ledger.close()
    reopened = PostTrainingLedger(tmp_path / "post.sqlite3")
    replacement = PostTrainingRunner(reopened)
    replacement.bind_execution(spec, **binding)
    receipt = replacement.run_episode(spec.run_id, episode_id="resumable", seed=7)
    assert calls == [1, 2, 2]
    assert receipt.steps == 2 and receipt.total_reward == 3
    assert replacement.run_episode(spec.run_id, episode_id="resumable", seed=7) == receipt
    assert calls == [1, 2, 2]


@pytest.mark.parametrize(
    "field",
    ["policy_digest", "model_digest", "curriculum_digest", "evaluation_suite_digest", "experiment_digest"],
)
def test_binding_rejects_changed_identity_before_policy_work(tmp_path, field):
    _, runner, spec, binding, _, _ = _fixture(tmp_path)
    with pytest.raises(PostTrainingExecutionError, match="identity mismatch"):
        runner.bind_execution(replace(spec, **{field: _sha("changed")}), **binding)
    assert runner.status(spec.run_id)["steps"] == 0


def test_restart_cannot_widen_bound_step_budget(tmp_path):
    _, runner, spec, binding, _, _ = _fixture(tmp_path)
    with pytest.raises(PostTrainingExecutionError, match="bound to different"):
        runner.bind_execution(replace(spec, max_steps=spec.max_steps + 1), **binding)


def test_versioned_environment_binds_actual_reward_logic(tmp_path):
    _, runner, spec, binding, _, _ = _fixture(tmp_path)
    binding["environment"].rewards["finish"] = 999.0
    with pytest.raises(PostTrainingExecutionError, match="environment behavior is immutable"):
        runner.bind_execution(spec, **binding)
    with pytest.raises(PostTrainingExecutionError, match="environment behavior is immutable"):
        runner.bind_execution(replace(spec, run_id="new-run-same-version"), **binding)


def test_replacement_runner_fences_previous_callbacks(tmp_path):
    ledger, first, spec, binding, _, _ = _fixture(tmp_path)
    replacement = PostTrainingRunner(ledger)
    replacement.bind_execution(spec, **binding)
    with pytest.raises(PostTrainingExecutionError, match="fenced"):
        first.run_episode(spec.run_id, episode_id="fenced")
    assert replacement.run_episode(spec.run_id, episode_id="replacement").steps == 2


def test_cumulative_step_budget_and_episode_budget_survive_reopen(tmp_path):
    ledger, runner, spec, binding, _, _ = _fixture(tmp_path, max_steps=1, max_episodes=1)
    episode = runner.run_episode(spec.run_id, episode_id="bounded")
    assert episode.status == "budget_exhausted" and episode.steps == 1
    assert runner.status(spec.run_id)["status"] == "budget_exhausted"
    ledger.close()
    reopened = PostTrainingLedger(tmp_path / "post.sqlite3")
    replacement = PostTrainingRunner(reopened)
    replacement.bind_execution(spec, **binding)
    with pytest.raises(PostTrainingExecutionError, match="budget_exhausted"):
        replacement.run_episode(spec.run_id, episode_id="extra")
    assert replacement.status(spec.run_id)["steps"] == 1
    assert replacement.status(spec.run_id)["episodes"] == 1


def test_episode_reservations_survive_restart_and_limit_new_episodes(tmp_path):
    ledger, runner, spec, binding, _, _ = _fixture(tmp_path, max_episodes=1)
    runner.run_episode(spec.run_id, episode_id="one")
    ledger.close()
    reopened = PostTrainingRunner(PostTrainingLedger(tmp_path / "post.sqlite3"))
    reopened.bind_execution(spec, **binding)
    with pytest.raises(PostTrainingExecutionError, match="episode budget"):
        reopened.run_episode(spec.run_id, episode_id="two")
    assert reopened.status(spec.run_id)["episodes"] == 1


def test_cancellation_preserves_committed_usage_and_blocks_curriculum(tmp_path):
    ledger, runner, spec, binding, _, _ = _fixture(tmp_path)
    checks = []

    def cancellation():
        checks.append(True)
        return len(checks) == 2

    episode = runner.run_episode(spec.run_id, episode_id="cancelled", cancelled=cancellation)
    assert episode.status == "cancelled" and episode.steps == 1
    assert runner.status(spec.run_id)["steps"] == 1
    with pytest.raises(PostTrainingExecutionError, match="inactive"):
        runner.evaluate_stage(
            spec.run_id,
            curriculum=binding["curriculum"],
            stage_id="reward",
            episode_refs=(episode.receipt_digest,),
        )
    assert ledger._db.execute("SELECT COUNT(*) FROM rl_step").fetchone()[0] == 1


def test_policy_cannot_request_undeclared_action_and_failed_work_rolls_back(tmp_path):
    def forbidden(observation):
        return "external-tool-write"

    _, runner, spec, _, _, _ = _fixture(tmp_path, callback=forbidden)
    with pytest.raises(PostTrainingExecutionError, match="declared authority"):
        runner.run_episode(spec.run_id, episode_id="denied")
    assert runner.status(spec.run_id)["steps"] == 0
    assert runner.status(spec.run_id)["episodes"] == 0


def test_caller_reported_rl_steps_cannot_forge_runtime_curriculum(tmp_path):
    ledger, runner, spec, binding, _, _ = _fixture(tmp_path)
    env = binding["environment"]
    env.reset(episode_id="reported", seed=0)
    reported = env.step("finish")
    ledger.record_step(reported)
    with pytest.raises(PostTrainingExecutionError, match="not issued"):
        runner.evaluate_stage(
            spec.run_id, curriculum=binding["curriculum"], stage_id="reward", episode_refs=(reported.digest,)
        )


def test_cross_policy_episode_evidence_is_rejected(tmp_path):
    _, runner, spec, binding, _, _ = _fixture(tmp_path)
    episode = runner.run_episode(spec.run_id, episode_id="original")
    other = replace(spec, run_id="other-execution")
    runner.bind_execution(other, **binding)
    with pytest.raises(PostTrainingExecutionError, match="not issued"):
        runner.evaluate_stage(
            other.run_id,
            curriculum=binding["curriculum"],
            stage_id="reward",
            episode_refs=(episode.receipt_digest,),
        )


def test_transition_and_usage_corruption_fail_closed(tmp_path):
    ledger, runner, spec, binding, _, _ = _fixture(tmp_path)
    episode = runner.run_episode(spec.run_id, episode_id="corrupt")
    row = ledger._db.execute("SELECT receipt_digest,payload FROM rl_step ORDER BY rowid LIMIT 1").fetchone()
    payload = json.loads(row[1])
    payload["reward"] = 1000
    ledger._db.execute("UPDATE rl_step SET payload=? WHERE receipt_digest=?", (json.dumps(payload), row[0]))
    ledger._db.commit()
    with pytest.raises(PostTrainingExecutionError, match="integrity"):
        runner.evaluate_stage(
            spec.run_id,
            curriculum=binding["curriculum"],
            stage_id="reward",
            episode_refs=(episode.receipt_digest,),
        )
    ledger._db.execute("UPDATE post_execution SET steps=0 WHERE run_id=?", (spec.run_id,))
    ledger._db.commit()
    with pytest.raises(PostTrainingExecutionError, match="usage integrity"):
        runner.status(spec.run_id)


@pytest.mark.asyncio
async def test_qualification_requires_measured_exact_suite_and_independent_verifier(tmp_path):
    _, runner, spec, binding, model, suite = _fixture(tmp_path)
    episode = runner.run_episode(spec.run_id, episode_id="measured")
    stages = _curriculum(runner, spec, binding, episode)
    with pytest.raises(PostTrainingExecutionError, match="independent"):
        await runner.evaluate_candidate(spec.run_id, model=model, suite=suite, verifier_id="trainer")
    with pytest.raises(PostTrainingExecutionError, match="identity mismatch"):
        await runner.evaluate_candidate(
            spec.run_id, model=model, suite=replace(suite, version="changed"), verifier_id="independent"
        )
    with pytest.raises(PostTrainingExecutionError, match="not issued"):
        runner.qualify_candidate(
            spec.run_id,
            curriculum_refs=tuple(item.receipt_digest for item in stages),
            evaluation_ref=_sha("fabricated-success"),
            verifier_id="independent",
        )
    evaluation = await runner.evaluate_candidate(
        spec.run_id, model=model, suite=suite, verifier_id="independent"
    )
    assert (
        await runner.evaluate_candidate(spec.run_id, model=model, suite=suite, verifier_id="independent")
        == evaluation
    )
    with pytest.raises(PostTrainingExecutionError, match="coverage"):
        runner.qualify_candidate(
            spec.run_id,
            curriculum_refs=(stages[0].receipt_digest,),
            evaluation_ref=evaluation.receipt_digest,
            verifier_id="independent",
        )


def test_prior_curriculum_corruption_cannot_unlock_prerequisite(tmp_path):
    ledger, runner, spec, binding, _, _ = _fixture(tmp_path)
    episode = runner.run_episode(spec.run_id, episode_id="prerequisite")
    first = runner.evaluate_stage(
        spec.run_id,
        curriculum=binding["curriculum"],
        stage_id="reward",
        episode_refs=(episode.receipt_digest,),
    )
    ledger._db.execute(
        "UPDATE post_curriculum_evidence SET payload='{}' WHERE receipt_digest=?", (first.receipt_digest,)
    )
    ledger._db.commit()
    with pytest.raises(PostTrainingExecutionError, match="curriculum evidence integrity"):
        runner.evaluate_stage(
            spec.run_id,
            curriculum=binding["curriculum"],
            stage_id="terminal",
            episode_refs=(episode.receipt_digest,),
        )


def test_mutated_callback_defaults_cannot_change_admitted_policy(tmp_path):
    def configurable(observation, threshold=1):
        return "wait" if observation.step <= threshold else "finish"

    _, runner, spec, _, _, _ = _fixture(tmp_path, callback=configurable)
    configurable.__defaults__ = (999,)
    with pytest.raises(PostTrainingExecutionError, match="policy identity changed"):
        runner.run_episode(spec.run_id, episode_id="changed-defaults")


def test_concurrent_episode_replays_commit_each_policy_transition_once(tmp_path, monkeypatch):
    calls = []
    original = DeterministicRLEnvironment.step

    def recorded(environment, action):
        calls.append(environment._step + 1)
        return original(environment, action)

    monkeypatch.setattr(DeterministicRLEnvironment, "step", recorded)
    _, runner, spec, _, _, _ = _fixture(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(runner.run_episode, spec.run_id, episode_id="concurrent") for _ in range(2)]
        receipts = [future.result() for future in futures]
    assert receipts[0] == receipts[1]
    assert calls == [1, 2]
    assert runner.status(spec.run_id)["steps"] == 2


def test_same_code_with_different_captured_action_has_different_policy_identity(tmp_path):
    def factory(action):
        def choose(observation):
            return action

        return choose

    _, runner, spec, binding, _, _ = _fixture(tmp_path, callback=factory("finish"))
    changed = replace(binding["policy"], decide=factory("wait"))
    assert changed.digest != binding["policy"].digest
    with pytest.raises(PostTrainingExecutionError, match="identity mismatch"):
        runner.bind_execution(spec, **{**binding, "policy": changed})


def test_policy_mutating_captured_state_cannot_publish_observed_transition(tmp_path):
    actions = ["finish"]

    def mutating(observation):
        action = actions.pop()
        return action

    _, runner, spec, _, _, _ = _fixture(tmp_path, callback=mutating)
    with pytest.raises(PostTrainingExecutionError, match="captured state changed"):
        runner.run_episode(spec.run_id, episode_id="mutable-policy")
    assert runner.status(spec.run_id)["steps"] == 0


def test_transition_storage_failure_rolls_back_cursor_receipt_and_usage(tmp_path):
    ledger, runner, spec, _, _, _ = _fixture(tmp_path)
    ledger._db.execute(
        "CREATE TRIGGER refuse_runtime_step BEFORE INSERT ON post_execution_step BEGIN SELECT RAISE(ABORT, 'injected storage failure'); END"
    )
    ledger._db.commit()
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError, match="storage failure"):
        runner.run_episode(spec.run_id, episode_id="storage-failure")
    assert runner.status(spec.run_id)["steps"] == 0
    assert runner.status(spec.run_id)["episodes"] == 0
    assert ledger._db.execute("SELECT COUNT(*) FROM rl_step").fetchone()[0] == 0
    ledger._db.execute("DROP TRIGGER refuse_runtime_step")
    ledger._db.commit()
    assert runner.run_episode(spec.run_id, episode_id="storage-failure").steps == 2


@pytest.mark.asyncio
async def test_model_evaluation_cannot_commit_after_cancellation(tmp_path, monkeypatch):
    from skeleton.ai.runtime.training import learning_pipeline

    ledger, runner, spec, _, model, suite = _fixture(tmp_path)
    evaluate = learning_pipeline.EvaluationHarness.evaluate

    async def cancellation_during_evaluation(harness, *args, **kwargs):
        result = await evaluate(harness, *args, **kwargs)
        runner.cancel(spec.run_id)
        return result

    monkeypatch.setattr(learning_pipeline.EvaluationHarness, "evaluate", cancellation_during_evaluation)
    with pytest.raises(PostTrainingExecutionError, match="cancelled or rebound"):
        await runner.evaluate_candidate(spec.run_id, model=model, suite=suite, verifier_id="independent")
    assert ledger._db.execute("SELECT COUNT(*) FROM post_evaluation_evidence").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_failed_measured_evaluation_rejects_candidate(tmp_path):
    ledger, runner, spec, binding, model, suite = _fixture(tmp_path)
    failed_suite = replace(suite, cases=(EvaluationCase("sum", "two plus two", "impossible-target", 3),))
    changed_experiment = replace(binding["experiment"], evaluation_suite_digest=failed_suite.digest)
    changed_spec = replace(
        spec,
        run_id="failed-evaluation",
        experiment_digest=changed_experiment.digest,
        evaluation_suite_digest=failed_suite.digest,
    )
    # A separate governed experiment identity prevents mutable experiment replay.
    changed_experiment = replace(changed_experiment, experiment_id="failed-experiment")
    changed_spec = replace(changed_spec, experiment_digest=changed_experiment.digest)
    changed_binding = {**binding, "experiment": changed_experiment}
    runner.bind_execution(changed_spec, **changed_binding)
    episode = runner.run_episode(changed_spec.run_id, episode_id="failed-benchmark-episode")
    stages = _curriculum(runner, changed_spec, changed_binding, episode)
    measured = await runner.evaluate_candidate(
        changed_spec.run_id, model=model, suite=failed_suite, verifier_id="independent"
    )
    assert measured.passed is False
    qualification = runner.qualify_candidate(
        changed_spec.run_id,
        curriculum_refs=tuple(stage.receipt_digest for stage in stages),
        evaluation_ref=measured.receipt_digest,
        verifier_id="independent",
    )
    assert qualification.status == "rejected"
    assert ledger._db.execute("SELECT COUNT(*) FROM post_qualification").fetchone()[0] == 1

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from skeleton.eval.experiment_registry import (
    ExperimentBudget,
    ExperimentEligibility,
    ExperimentManifest,
    ExperimentMetric,
    MetricDirection,
    TrafficMode,
)
from skeleton.learning.mirror_room import (
    EpisodeOutcome,
    MirrorBudget,
    MirrorCandidate,
    MirrorMetricPolicy,
    MirrorRoom,
    MirrorRoomError,
    MirrorRoomSpec,
    MirrorSandbox,
    MirrorScenario,
    SandboxPolicy,
    ScenarioSplit,
    qualify_for_external_promotion,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _candidate(
    candidate_id: str,
    skill: float,
    *,
    parent: str | None = None,
    producer: str = "mirror-generator",
) -> MirrorCandidate:
    return MirrorCandidate(
        candidate_id=candidate_id,
        version="version-" + candidate_id,
        producer_id=producer,
        change_ref="change:" + candidate_id,
        change_digest=_sha(f"{candidate_id}:{skill}"),
        parameters={"skill": skill},
        parent_candidate_id=parent,
        evidence_refs=("proposal:" + candidate_id,),
    )


def _manifest(
    *,
    traffic_mode: TrafficMode = TrafficMode.OFFLINE,
) -> ExperimentManifest:
    return ExperimentManifest(
        experiment_id="exp.reverse.mirror.core.v1",
        hypothesis="A bounded offline candidate improves quality without safety regression.",
        owner="reverse-functional-ai",
        source_commit="a" * 40,
        environment_id="mirror.offline.core",
        candidate_ref="candidate:reverse-mirror-core",
        eligibility=ExperimentEligibility(
            traffic_mode=traffic_mode,
            max_traffic_fraction=(
                0.0 if traffic_mode is TrafficMode.OFFLINE else 0.1
            ),
            allowed_data_classes=("public",),
            tenant_ids=(),
            external_side_effects_allowed=False,
        ),
        budget=ExperimentBudget(
            max_samples=128,
            max_tokens=4096,
            max_cost_units=4.0,
            max_wall_time_s=300.0,
        ),
        metrics=(
            ExperimentMetric(
                metric_id="quality",
                direction=MetricDirection.MAXIMIZE,
                minimum_samples=1,
                source="independent-quality-evaluator",
            ),
            ExperimentMetric(
                metric_id="safety",
                direction=MetricDirection.MAXIMIZE,
                minimum_samples=1,
                source="independent-safety-evaluator",
            ),
        ),
        tags=("mirror-room", "reverse-functional-ai"),
    )


def _spec(
    *,
    manifest: ExperimentManifest | None = None,
    max_episodes: int = 64,
) -> MirrorRoomSpec:
    return MirrorRoomSpec(
        manifest=manifest or _manifest(),
        production_baseline=_candidate(
            "production-v1",
            0.20,
            producer="release-authority",
        ),
        metrics=(
            MirrorMetricPolicy(
                metric_id="quality",
                direction=MetricDirection.MAXIMIZE,
                minimum_improvement=0.01,
                confidence_level=0.95,
                weight=2.0,
            ),
            MirrorMetricPolicy(
                metric_id="safety",
                direction=MetricDirection.MAXIMIZE,
                max_regression=0.0,
                confidence_level=0.95,
                guardrail=True,
            ),
        ),
        sandbox_policy=SandboxPolicy(
            allowed_capabilities=("compute",),
            max_steps_per_episode=4,
            max_tokens_per_episode=32,
            max_cost_units_per_episode=0.05,
        ),
        budget=MirrorBudget(
            max_generations=2,
            max_candidates_per_generation=1,
            max_episodes=max_episodes,
            max_total_steps=256,
            max_total_tokens=2048,
            max_total_cost_units=2.0,
            max_validation_candidate_evaluations=2,
        ),
        hard_example_limit=2,
        stagnation_patience=2,
    )


def _scenarios() -> tuple[MirrorScenario, ...]:
    return (
        MirrorScenario(
            "train-1",
            ScenarioSplit.TRAIN,
            {"difficulty": 0.00, "case": "train"},
        ),
        MirrorScenario(
            "validation-1",
            ScenarioSplit.VALIDATION,
            {"difficulty": 0.05, "case": "validation"},
        ),
        MirrorScenario(
            "holdout-1",
            ScenarioSplit.HOLDOUT,
            {"difficulty": 0.10, "case": "holdout"},
        ),
    )


class Executor:
    executor_id = "independent-mirror-evaluator"

    def __init__(
        self,
        *,
        unsafe: bool = False,
        holdout_penalty: float = 0.0,
        diverge: bool = False,
    ) -> None:
        self.unsafe = unsafe
        self.holdout_penalty = holdout_penalty
        self.diverge = diverge
        self.counter = 0
        self.calls: list[tuple[str, str, int]] = []

    def execute(self, *, candidate, scenario, seed, policy):
        self.counter += 1
        self.calls.append(
            (candidate.candidate_id, scenario.scenario_id, seed)
        )
        score = 0.50 + float(candidate.parameters["skill"])
        score -= float(scenario.payload["difficulty"])
        if (
            scenario.split is ScenarioSplit.HOLDOUT
            and candidate.parent_candidate_id is not None
        ):
            score -= self.holdout_penalty
        score = max(0.0, min(1.0, score))
        salt = self.counter if self.diverge else 0
        return EpisodeOutcome(
            metric_values={"quality": score, "safety": 0.95},
            observation_digest=_sha(
                f"{candidate.digest}:{scenario.digest}:{seed}:{salt}"
            ),
            steps=1,
            tokens=4,
            cost_units=0.01,
            capabilities_used=("network",) if self.unsafe else ("compute",),
        )


class Generator:
    generator_id = "mirror-generator"

    def __init__(self, *, step: float = 0.10) -> None:
        self.step = step
        self.feedback = []

    def propose(self, feedback, *, limit):
        self.feedback.append(feedback)
        skill = float(feedback.champion.parameters["skill"]) + self.step
        return (
            _candidate(
                f"candidate-{feedback.generation}",
                skill,
                parent=feedback.champion.candidate_id,
            ),
        )[:limit]


def _run(
    *,
    executor: Executor | None = None,
    generations: int = 2,
    spec: MirrorRoomSpec | None = None,
):
    actual_spec = spec or _spec()
    actual_executor = executor or Executor()
    generator = Generator()
    receipt = MirrorRoom(actual_spec, actual_executor).learn(
        run_id="reverse-mirror-run",
        generator=generator,
        scenarios=_scenarios(),
        generations=generations,
    )
    return actual_spec, actual_executor, generator, receipt


def test_mirror_room_requires_offline_zero_traffic() -> None:
    with pytest.raises(MirrorRoomError, match="offline"):
        _spec(manifest=_manifest(traffic_mode=TrafficMode.SHADOW))


def test_iterative_learning_keeps_holdout_sealed_until_final_candidate() -> None:
    spec, executor, generator, receipt = _run(generations=2)

    assert receipt.final_sandbox_champion.candidate_id == "candidate-2"
    assert receipt.final_sandbox_champion != spec.production_baseline
    assert receipt.holdout_report is not None
    assert receipt.holdout_report.passed is True
    assert receipt.eligible_for_external_promotion is True
    assert receipt.production_authority is False
    assert receipt.direct_self_modify is False

    assert len(generator.feedback) == 2
    assert all(
        scenario.split is ScenarioSplit.TRAIN
        for feedback in generator.feedback
        for scenario in feedback.training_scenarios
    )
    holdout_calls = [
        call for call in executor.calls
        if call[1] == "holdout-1"
    ]
    assert [call[0] for call in holdout_calls] == [
        "production-v1",
        "candidate-2",
    ]


def test_paired_validation_uses_same_seed_for_baseline_and_candidate() -> None:
    _, executor, _, _ = _run(generations=1)
    validation = [
        call for call in executor.calls
        if call[1] == "validation-1"
    ]
    assert len(validation) == 2
    assert validation[0][2] == validation[1][2]


def test_sealed_holdout_can_veto_validation_winner() -> None:
    _, _, _, receipt = _run(
        executor=Executor(holdout_penalty=0.80),
        generations=1,
    )
    assert receipt.final_sandbox_champion.candidate_id == "candidate-1"
    assert receipt.holdout_report is not None
    assert receipt.holdout_report.passed is False
    assert receipt.eligible_for_external_promotion is False


def test_forbidden_capability_fails_closed() -> None:
    with pytest.raises(MirrorRoomError, match="forbidden capabilities"):
        _run(executor=Executor(unsafe=True), generations=1)


def test_whole_run_budget_fails_closed() -> None:
    with pytest.raises(MirrorRoomError, match="episode budget exhausted"):
        _run(spec=_spec(max_episodes=3), generations=1)


def test_replay_detects_nondeterministic_executor() -> None:
    spec = _spec()
    sandbox = MirrorSandbox(spec, Executor(diverge=True))
    scenario = _scenarios()[0]
    receipt = sandbox.run_episode(
        run_id="replay-run",
        candidate=spec.production_baseline,
        scenario=scenario,
    )
    with pytest.raises(MirrorRoomError, match="replay diverged"):
        sandbox.verify_replay(
            receipt,
            candidate=spec.production_baseline,
            scenario=scenario,
        )


def test_split_contamination_is_rejected_before_learning() -> None:
    duplicate = {"difficulty": 0.10, "case": "same"}
    scenarios = (
        MirrorScenario("train-dup", ScenarioSplit.TRAIN, duplicate),
        MirrorScenario(
            "validation-ok",
            ScenarioSplit.VALIDATION,
            {"difficulty": 0.20, "case": "validation"},
        ),
        MirrorScenario("holdout-dup", ScenarioSplit.HOLDOUT, duplicate),
    )
    with pytest.raises(
        MirrorRoomError,
        match="split contamination|duplicate scenario payload",
    ):
        MirrorRoom(_spec(), Executor()).learn(
            run_id="contaminated",
            generator=Generator(),
            scenarios=scenarios,
            generations=1,
        )


def test_promotion_handoff_requires_independent_verifier_and_rollback() -> None:
    _, _, _, receipt = _run(generations=1)

    with pytest.raises(
        MirrorRoomError,
        match="producer cannot independently verify|independent",
    ):
        qualify_for_external_promotion(
            receipt,
            verifier_id="mirror-generator",
            evaluation_refs=("eval:quality", "eval:safety"),
            verified_at=10,
        )

    evidence = qualify_for_external_promotion(
        receipt,
        verifier_id="independent-promotion-verifier",
        evaluation_refs=("eval:quality", "eval:safety"),
        verified_at=10,
    )
    assert evidence.production_authority is False
    assert evidence.direct_self_modify is False
    assert evidence.candidate_id == receipt.final_sandbox_champion.candidate_id
    assert (
        evidence.rollback_candidate_id
        == receipt.production_baseline.candidate_id
    )
    assert len(evidence.digest) == 64


def test_core_source_and_ai_mirror_are_byte_identical() -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton" / "learning" / "mirror_room"
    mirror = root / "skeleton" / "ai" / "learning" / "mirror_room"
    names = (
        "__init__.py",
        "contracts.py",
        "sandbox.py",
        "evaluation.py",
        "curriculum.py",
        "integrity.py",
        "engine.py",
        "promotion.py",
    )
    assert all(
        (source / name).read_bytes() == (mirror / name).read_bytes()
        for name in names
    )


def test_run_receipt_rejects_forged_holdout_candidate_identity() -> None:
    _, _, _, receipt = _run(generations=1)
    assert receipt.holdout_report is not None
    forged_report = replace(
        receipt.holdout_report,
        candidate_id=receipt.production_baseline.candidate_id,
        candidate_digest=receipt.production_baseline.digest,
    )
    with pytest.raises(MirrorRoomError, match="holdout report candidate identity mismatch"):
        replace(receipt, holdout_report=forged_report)


def test_run_receipt_rejects_forged_holdout_baseline_identity() -> None:
    _, _, _, receipt = _run(generations=1)
    assert receipt.holdout_report is not None
    forged_report = replace(
        receipt.holdout_report,
        baseline_candidate_id=receipt.final_sandbox_champion.candidate_id,
        baseline_candidate_digest=receipt.final_sandbox_champion.digest,
    )
    with pytest.raises(MirrorRoomError, match="holdout report baseline identity mismatch"):
        replace(receipt, holdout_report=forged_report)


def test_run_receipt_rejects_holdout_from_another_run() -> None:
    _, _, _, receipt = _run(generations=1)
    assert receipt.holdout_report is not None
    forged_report = replace(receipt.holdout_report, run_id="other-run")
    with pytest.raises(MirrorRoomError, match="holdout report run identity mismatch"):
        replace(receipt, holdout_report=forged_report)


def test_promotion_rejects_forged_selected_validation_candidate() -> None:
    _, _, _, receipt = _run(generations=1)
    generation = receipt.generations[0]
    selected = next(item for item in generation.evaluations if item.selected)
    forged_validation = replace(
        selected.validation_report,
        candidate_id=receipt.production_baseline.candidate_id,
        candidate_digest=receipt.production_baseline.digest,
    )
    forged_evaluation = replace(
        selected,
        validation_report=forged_validation,
    )
    forged_generation = replace(
        generation,
        evaluations=tuple(
            forged_evaluation if item is selected else item
            for item in generation.evaluations
        ),
    )
    forged_receipt = replace(receipt, generations=(forged_generation,))

    with pytest.raises(
        MirrorRoomError,
        match="selected validation candidate identity mismatch",
    ):
        qualify_for_external_promotion(
            forged_receipt,
            verifier_id="independent-promotion-verifier",
            evaluation_refs=("eval:quality", "eval:safety"),
            verified_at=10,
        )


def test_promotion_evidence_rejects_noncanonical_digest_and_rollback_drift() -> None:
    _, _, _, receipt = _run(generations=1)
    evidence = qualify_for_external_promotion(
        receipt,
        verifier_id="independent-promotion-verifier",
        evaluation_refs=("eval:quality", "eval:safety"),
        verified_at=10,
    )

    with pytest.raises(MirrorRoomError, match="candidate_digest"):
        replace(evidence, candidate_digest="g" * 64)

    with pytest.raises(MirrorRoomError, match="rollback candidate"):
        replace(
            evidence,
            rollback_candidate_id=evidence.candidate_id,
            rollback_candidate_digest=evidence.candidate_digest,
        )


def test_episode_replay_rejects_candidate_metadata_substitution() -> None:
    spec = _spec()
    sandbox = MirrorSandbox(spec, Executor())
    scenario = _scenarios()[0]
    receipt = sandbox.run_episode(
        run_id="episode-binding",
        candidate=spec.production_baseline,
        scenario=scenario,
    )
    forged = replace(receipt, candidate_id="forged-candidate")
    with pytest.raises(MirrorRoomError, match="replay candidate identity changed"):
        sandbox.verify_replay(
            forged,
            candidate=spec.production_baseline,
            scenario=scenario,
        )


def test_episode_replay_rejects_scenario_metadata_and_split_substitution() -> None:
    spec = _spec()
    scenario = _scenarios()[0]

    sandbox = MirrorSandbox(spec, Executor())
    receipt = sandbox.run_episode(
        run_id="episode-binding",
        candidate=spec.production_baseline,
        scenario=scenario,
    )
    forged_scenario = replace(receipt, scenario_id="forged-scenario")
    with pytest.raises(MirrorRoomError, match="replay scenario identity changed"):
        sandbox.verify_replay(
            forged_scenario,
            candidate=spec.production_baseline,
            scenario=scenario,
        )

    split_sandbox = MirrorSandbox(spec, Executor())
    split_receipt = split_sandbox.run_episode(
        run_id="episode-binding-split",
        candidate=spec.production_baseline,
        scenario=scenario,
    )
    forged_split = replace(split_receipt, split=ScenarioSplit.VALIDATION.value)
    with pytest.raises(MirrorRoomError, match="replay scenario split changed"):
        split_sandbox.verify_replay(
            forged_split,
            candidate=spec.production_baseline,
            scenario=scenario,
        )


def test_episode_receipt_rejects_noncanonical_digest_metadata() -> None:
    spec = _spec()
    sandbox = MirrorSandbox(spec, Executor())
    scenario = _scenarios()[0]
    receipt = sandbox.run_episode(
        run_id="episode-binding",
        candidate=spec.production_baseline,
        scenario=scenario,
    )
    with pytest.raises(MirrorRoomError, match="candidate_digest"):
        replace(receipt, candidate_digest="G" * 64)

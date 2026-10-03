from __future__ import annotations

import hashlib

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
    ADVERSARIAL_ATTEMPTS_REQUIRED,
    AdversarialMirrorRoom,
    AdversarialRatchetPolicy,
    EpisodeOutcome,
    FixedAdversarialSuite,
    MirrorBudget,
    MirrorCandidate,
    MirrorMetricPolicy,
    MirrorRoomError,
    MirrorRoomSpec,
    MirrorScenario,
    SandboxPolicy,
    ScenarioSplit,
    qualify_adversarial_delivery,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _candidate(
    candidate_id: str,
    skill: float,
    *,
    parent: str | None,
) -> MirrorCandidate:
    return MirrorCandidate(
        candidate_id=candidate_id,
        version=f"version-{candidate_id}",
        producer_id="ratchet-learner",
        change_ref=f"change:{candidate_id}",
        change_digest=_sha(f"{candidate_id}:{skill:.12f}"),
        parameters={"skill": skill},
        parent_candidate_id=parent,
        evidence_refs=(f"proposal:{candidate_id}",),
    )


def _spec() -> MirrorRoomSpec:
    manifest = ExperimentManifest(
        experiment_id="exp.adversarial-ratchet.v1",
        hypothesis=(
            "One hundred adversarial attempts ratchet quality without "
            "regressing safety."
        ),
        owner="p1-learning",
        source_commit="a" * 40,
        environment_id="mirror.adversarial.offline",
        candidate_ref="candidate:adversarial-ratchet.v1",
        eligibility=ExperimentEligibility(
            traffic_mode=TrafficMode.OFFLINE,
            max_traffic_fraction=0.0,
            allowed_data_classes=("public",),
            tenant_ids=(),
            external_side_effects_allowed=False,
        ),
        budget=ExperimentBudget(
            max_samples=12_000,
            max_tokens=500_000,
            max_cost_units=800.0,
            max_wall_time_s=7200.0,
        ),
        metrics=(
            ExperimentMetric(
                metric_id="quality.acceptance",
                direction=MetricDirection.MAXIMIZE,
                minimum_samples=1,
                source="independent-eval",
            ),
            ExperimentMetric(
                metric_id="safety.score",
                direction=MetricDirection.MAXIMIZE,
                minimum_samples=1,
                source="independent-safety-eval",
            ),
        ),
        parent_experiment_id=None,
        tags=("mirror-room", "adversarial", "ratchet"),
    )
    return MirrorRoomSpec(
        manifest=manifest,
        production_baseline=MirrorCandidate(
            candidate_id="production-v1",
            version="version-production-v1",
            producer_id="release",
            change_ref="change:production-v1",
            change_digest=_sha("production-v1:0.2"),
            parameters={"skill": 0.2},
        ),
        metrics=(
            MirrorMetricPolicy(
                metric_id="quality.acceptance",
                direction=MetricDirection.MAXIMIZE,
                minimum_improvement=0.001,
                confidence_level=0.95,
                weight=2.0,
            ),
            MirrorMetricPolicy(
                metric_id="safety.score",
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
            max_generations=100,
            max_candidates_per_generation=1,
            max_episodes=12_000,
            max_total_steps=48_000,
            max_total_tokens=384_000,
            max_total_cost_units=600.0,
        ),
        hard_example_limit=8,
        stagnation_patience=100,
    )


def _base_scenarios() -> tuple[MirrorScenario, ...]:
    return (
        MirrorScenario(
            "train-base",
            ScenarioSplit.TRAIN,
            {"difficulty": 0.05, "kind": "base-train"},
        ),
        MirrorScenario(
            "validation-base",
            ScenarioSplit.VALIDATION,
            {"difficulty": 0.10, "kind": "validation"},
        ),
        MirrorScenario(
            "holdout-base",
            ScenarioSplit.HOLDOUT,
            {"difficulty": 0.15, "kind": "holdout"},
        ),
    )


def _challenges(count: int = 100) -> tuple[MirrorScenario, ...]:
    return tuple(
        MirrorScenario(
            scenario_id=f"attack-{index + 1:03d}",
            split=ScenarioSplit.TRAIN,
            payload={
                "difficulty": 0.06 + (index * 0.0001),
                "kind": "fresh-adversarial",
                "attempt": index + 1,
            },
            tags=("adversarial",),
        )
        for index in range(count)
    )


class RatchetExecutor:
    executor_id = "independent-ratchet-evaluator"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    def execute(self, *, candidate, scenario, seed, policy):
        self.calls.append(
            (candidate.candidate_id, scenario.scenario_id, seed)
        )
        skill = float(candidate.parameters["skill"])
        difficulty = float(scenario.payload["difficulty"])
        quality = min(1.0, max(0.0, 0.5 + skill - difficulty))
        return EpisodeOutcome(
            metric_values={
                "quality.acceptance": quality,
                "safety.score": 0.95,
            },
            observation_digest=_sha(
                f"{candidate.digest}:{scenario.digest}:{seed}"
            ),
            steps=1,
            tokens=8,
            cost_units=0.01,
            capabilities_used=("compute",),
        )


class HundredStepGenerator:
    generator_id = "ratchet-learner"

    def __init__(self, *, step: float = 0.0015) -> None:
        self.step = step
        self.calls = 0
        self.baselines: list[str] = []

    def propose(self, feedback, *, limit):
        self.calls += 1
        self.baselines.append(feedback.champion.candidate_id)
        skill = float(feedback.champion.parameters["skill"])
        return (
            _candidate(
                f"attempt-{self.calls:03d}",
                skill + self.step,
                parent=feedback.champion.candidate_id,
            ),
        )


class ThreeAttemptGenerator:
    generator_id = "ratchet-learner"

    def __init__(self) -> None:
        self.calls = 0

    def propose(self, feedback, *, limit):
        self.calls += 1
        skill = float(feedback.champion.parameters["skill"])
        delta = {1: 0.002, 2: -0.05, 3: 0.002}[self.calls]
        return (
            _candidate(
                f"mixed-{self.calls}",
                skill + delta,
                parent=feedback.champion.candidate_id,
            ),
        )


def _room(
    executor: RatchetExecutor | None = None,
    *,
    challenges: tuple[MirrorScenario, ...] | None = None,
) -> tuple[AdversarialMirrorRoom, RatchetExecutor]:
    actual_executor = executor or RatchetExecutor()
    adversary = FixedAdversarialSuite(
        adversary_id="independent-red-team",
        challenges=challenges or _challenges(),
    )
    return (
        AdversarialMirrorRoom(
            _spec(),
            actual_executor,
            adversary,
            policy=AdversarialRatchetPolicy(),
        ),
        actual_executor,
    )


def test_policy_requires_exactly_one_hundred_attempts() -> None:
    assert AdversarialRatchetPolicy().attempts_required == 100
    with pytest.raises(MirrorRoomError, match="exactly 100"):
        AdversarialRatchetPolicy(attempts_required=99)


def test_full_campaign_ratchets_baseline_for_all_100_attempts() -> None:
    room, _ = _room()
    generator = HundredStepGenerator()

    receipt = room.run(
        run_id="ratchet-100",
        generator=generator,
        scenarios=_base_scenarios(),
    )

    assert receipt.completed_attempts == ADVERSARIAL_ATTEMPTS_REQUIRED
    assert receipt.accepted_upgrades == 100
    assert receipt.delivery_ready is True
    assert receipt.gauntlet_report is not None
    assert receipt.gauntlet_report.passed is True
    assert len(receipt.gauntlet_report.scenario_comparisons) == 101
    assert generator.calls == 100
    assert generator.baselines[0] == "production-v1"
    assert generator.baselines[1] == "attempt-001"
    assert generator.baselines[-1] == "attempt-099"
    assert receipt.final_baseline.candidate_id == "attempt-100"

    previous = receipt.original_baseline.digest
    for attempt in receipt.attempts:
        assert attempt.baseline_before.digest == previous
        assert attempt.accepted is True
        assert attempt.baseline_after.digest == attempt.candidate.digest
        previous = attempt.baseline_after.digest


def test_validation_standard_floors_increase_monotonically() -> None:
    room, _ = _room()
    receipt = room.run(
        run_id="ratchet-floors",
        generator=HundredStepGenerator(),
        scenarios=_base_scenarios(),
    )

    quality_floors = [
        attempt.standard_after.metric_floors["quality.acceptance"]
        for attempt in receipt.attempts
    ]
    assert quality_floors == sorted(quality_floors)
    assert all(
        right > left
        for left, right in zip(
            quality_floors,
            quality_floors[1:],
        )
    )


def test_rejected_attempt_never_lowers_or_replaces_baseline() -> None:
    room, _ = _room()
    receipt = room.run(
        run_id="ratchet-rejection",
        generator=ThreeAttemptGenerator(),
        scenarios=_base_scenarios(),
        attempts=3,
    )

    first, second, third = receipt.attempts
    assert first.accepted is True
    assert second.accepted is False
    assert second.baseline_after.digest == first.baseline_after.digest
    assert second.rejection_reasons
    assert third.baseline_before.digest == first.baseline_after.digest
    assert third.accepted is True
    assert receipt.delivery_ready is False
    assert receipt.holdout_report is None


def test_partial_campaign_cannot_touch_holdout_or_deliver() -> None:
    room, executor = _room()
    receipt = room.run(
        run_id="ratchet-partial",
        generator=HundredStepGenerator(),
        scenarios=_base_scenarios(),
        attempts=3,
    )

    assert receipt.completed_attempts == 3
    assert receipt.delivery_ready is False
    assert receipt.gauntlet_report is None
    assert receipt.holdout_report is None
    assert all(
        scenario_id != "holdout-base"
        for _, scenario_id, _ in executor.calls
    )
    with pytest.raises(MirrorRoomError, match="not ready"):
        qualify_adversarial_delivery(
            receipt,
            verifier_id="delivery-verifier",
            evaluation_refs=("eval:red-team", "eval:holdout"),
            verified_at=100,
        )


def test_holdout_is_opened_only_after_attempt_100() -> None:
    room, executor = _room()
    receipt = room.run(
        run_id="ratchet-holdout",
        generator=HundredStepGenerator(),
        scenarios=_base_scenarios(),
    )

    holdout_calls = [
        call
        for call in executor.calls
        if call[1] == "holdout-base"
    ]
    assert receipt.completed_attempts == 100
    assert len(holdout_calls) == 2
    assert [call[0] for call in holdout_calls] == [
        "production-v1",
        "attempt-100",
    ]


def test_delivery_evidence_requires_independent_verifier() -> None:
    room, _ = _room()
    receipt = room.run(
        run_id="ratchet-delivery",
        generator=HundredStepGenerator(),
        scenarios=_base_scenarios(),
    )

    with pytest.raises(MirrorRoomError, match="independent"):
        qualify_adversarial_delivery(
            receipt,
            verifier_id="independent-red-team",
            evaluation_refs=("eval:red-team", "eval:holdout"),
            verified_at=100,
        )

    evidence = qualify_adversarial_delivery(
        receipt,
        verifier_id="delivery-verifier",
        evaluation_refs=("eval:red-team", "eval:holdout"),
        verified_at=100,
    )
    assert evidence.attempts_completed == 100
    assert evidence.accepted_upgrades == 100
    assert evidence.final_candidate_id == "attempt-100"
    assert evidence.gauntlet_report_digest == receipt.gauntlet_report.digest
    assert evidence.rollback_candidate_id == "production-v1"
    assert evidence.production_authority is False
    assert (
        evidence.evidence_ref().category
        == "mirror_room_adversarial_delivery"
    )


def test_adversary_receives_no_validation_or_holdout_payloads() -> None:
    class InspectingAdversary:
        adversary_id = "independent-red-team"

        def __init__(self) -> None:
            self.contexts = []

        def challenge(self, context, *, limit):
            self.contexts.append(context)
            return (
                MirrorScenario(
                    f"inspect-{context.attempt}",
                    ScenarioSplit.TRAIN,
                    {
                        "difficulty": 0.06,
                        "attempt": context.attempt,
                        "kind": "inspect",
                    },
                ),
            )

    adversary = InspectingAdversary()
    room = AdversarialMirrorRoom(
        _spec(),
        RatchetExecutor(),
        adversary,
    )
    receipt = room.run(
        run_id="ratchet-context",
        generator=HundredStepGenerator(),
        scenarios=_base_scenarios(),
        attempts=3,
    )

    assert receipt.completed_attempts == 3
    assert len(adversary.contexts) == 3
    for context in adversary.contexts:
        assert all(
            item.split is ScenarioSplit.TRAIN
            for item in context.training_scenarios
        )
        assert not hasattr(context, "validation_scenarios")
        assert not hasattr(context, "holdout_scenarios")


def test_adversarial_challenges_must_be_fresh_across_attempts() -> None:
    repeated = tuple(
        MirrorScenario(
            f"reused-{index}",
            ScenarioSplit.TRAIN,
            {
                "difficulty": 0.06,
                "kind": "same-payload",
            },
        )
        for index in range(100)
    )
    with pytest.raises(MirrorRoomError, match="payloads must be unique"):
        FixedAdversarialSuite(
            adversary_id="independent-red-team",
            challenges=repeated,
        )


def test_campaign_requires_capacity_for_all_100_attempts_upfront() -> None:
    spec = _spec()
    undersized = MirrorRoomSpec(
        manifest=spec.manifest,
        production_baseline=spec.production_baseline,
        metrics=spec.metrics,
        sandbox_policy=spec.sandbox_policy,
        budget=MirrorBudget(
            max_generations=100,
            max_candidates_per_generation=1,
            max_episodes=100,
            max_total_steps=48_000,
            max_total_tokens=384_000,
            max_total_cost_units=600.0,
        ),
        hard_example_limit=spec.hard_example_limit,
        stagnation_patience=100,
    )
    room = AdversarialMirrorRoom(
        undersized,
        RatchetExecutor(),
        FixedAdversarialSuite(
            adversary_id="independent-red-team",
            challenges=_challenges(),
        ),
    )
    with pytest.raises(MirrorRoomError, match="episode budget"):
        room.run(
            run_id="ratchet-budget",
            generator=HundredStepGenerator(),
            scenarios=_base_scenarios(),
            attempts=1,
        )


def test_campaign_rejects_identity_collapse_between_roles() -> None:
    class CollidingAdversary(FixedAdversarialSuite):
        pass

    room = AdversarialMirrorRoom(
        _spec(),
        RatchetExecutor(),
        CollidingAdversary(
            adversary_id="ratchet-learner",
            challenges=_challenges(),
        ),
    )
    with pytest.raises(MirrorRoomError, match="must be independent"):
        room.run(
            run_id="ratchet-role-collision",
            generator=HundredStepGenerator(),
            scenarios=_base_scenarios(),
            attempts=1,
        )

def test_ratchet_rejects_candidate_without_meaningful_strict_metric_lift() -> None:
    executor = RatchetExecutor()
    room = AdversarialMirrorRoom(
        _spec(),
        executor,
        FixedAdversarialSuite(
            adversary_id="independent-red-team",
            challenges=_challenges(),
        ),
        policy=AdversarialRatchetPolicy(
            minimum_strict_metric_gain=0.01,
        ),
    )
    receipt = room.run(
        run_id="ratchet-strict-lift",
        generator=HundredStepGenerator(step=0.0015),
        scenarios=_base_scenarios(),
        attempts=1,
    )

    attempt = receipt.attempts[0]
    assert attempt.accepted is False
    assert attempt.baseline_after.digest == receipt.original_baseline.digest
    assert any(
        "insufficient-strict-metric-lift" in reason
        for reason in attempt.rejection_reasons
    )

def test_progressive_standard_bar_escalates_across_all_100_attempts() -> None:
    room, _ = _room()
    receipt = room.run(
        run_id="ratchet-progressive-standard",
        generator=HundredStepGenerator(),
        scenarios=_base_scenarios(),
    )

    weighted = [
        item.required_weighted_gain
        for item in receipt.attempts
    ]
    strict = [
        item.required_strict_metric_gain
        for item in receipt.attempts
    ]
    assert weighted == sorted(weighted)
    assert strict == sorted(strict)
    assert weighted[-1] > weighted[0]
    assert strict[-1] > strict[0]
    assert weighted[-1] == pytest.approx(
        receipt.policy.final_minimum_weighted_gain
    )
    assert strict[-1] == pytest.approx(
        receipt.policy.final_minimum_strict_metric_gain
    )


def test_every_attempt_retests_entire_discovered_attack_corpus() -> None:
    room, _ = _room()
    receipt = room.run(
        run_id="ratchet-retention-memory",
        generator=HundredStepGenerator(),
        scenarios=_base_scenarios(),
    )

    # One base TRAIN scenario plus every adversarial challenge discovered so far.
    assert [
        len(item.retention_scenario_digests)
        for item in receipt.attempts
    ] == list(range(2, 102))
    previous = set()
    for item in receipt.attempts:
        current = set(item.retention_scenario_digests)
        if previous:
            assert previous < current
            assert current - previous == set(item.challenge_digests)
        previous = current
    assert len(
        receipt.attempts[-1].challenge_report.scenario_comparisons
    ) == 101


def test_custom_progressive_bar_can_reject_late_marginal_upgrades() -> None:
    room = AdversarialMirrorRoom(
        _spec(),
        RatchetExecutor(),
        FixedAdversarialSuite(
            adversary_id="independent-red-team",
            challenges=_challenges(),
        ),
        policy=AdversarialRatchetPolicy(
            final_minimum_weighted_gain=0.0012,
            final_minimum_strict_metric_gain=0.0020,
        ),
    )
    receipt = room.run(
        run_id="ratchet-progressive-rejection",
        generator=HundredStepGenerator(),
        scenarios=_base_scenarios(),
    )

    assert any(item.accepted for item in receipt.attempts[:25])
    assert any(not item.accepted for item in receipt.attempts[-25:])
    assert receipt.attempts[-1].required_weighted_gain > (
        receipt.attempts[0].required_weighted_gain
    )

class BrokenObservatory:
    def begin(self, **kwargs):
        raise RuntimeError("ui unavailable")

    def record_attempt(self, receipt):
        raise RuntimeError("ui unavailable")

    def finish(self, campaign):
        raise RuntimeError("ui unavailable")


def test_observatory_failure_cannot_block_or_influence_learning() -> None:
    executor = RatchetExecutor()
    adversary = FixedAdversarialSuite(
        adversary_id="independent-red-team",
        challenges=_challenges(),
    )
    room = AdversarialMirrorRoom(
        _spec(),
        executor,
        adversary,
        policy=AdversarialRatchetPolicy(),
        observatory=BrokenObservatory(),
    )

    receipt = room.run(
        run_id="observer-isolation",
        generator=HundredStepGenerator(),
        scenarios=_base_scenarios(),
        attempts=3,
    )

    assert receipt.completed_attempts == 3
    assert receipt.accepted_upgrades == 3
    assert receipt.final_baseline.candidate_id == "attempt-003"

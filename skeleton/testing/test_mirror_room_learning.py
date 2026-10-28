from __future__ import annotations

import hashlib
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
    CurriculumPolicy,
    DeterministicCoordinateLearner,
    EpisodeOutcome,
    HardExample,
    MirrorBudget,
    MirrorCandidate,
    MirrorMetricPolicy,
    MirrorRoom,
    MirrorRoomError,
    MirrorRoomSpec,
    MirrorSandbox,
    MirrorScenario,
    NumericDimension,
    SandboxPolicy,
    ScenarioSplit,
    SplitIntegrityPolicy,
    TrainingLearningArchive,
    build_curriculum,
    inspect_split_integrity,
    qualify_for_external_promotion,
    verify_selected_lineage,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _candidate(
    cid: str,
    skill: float,
    parent: str | None = None,
    producer: str = "learner",
) -> MirrorCandidate:
    return MirrorCandidate(
        candidate_id=cid,
        version=f"version-{cid}",
        producer_id=producer,
        change_ref=f"change:{cid}",
        change_digest=_sha(f"{cid}:{skill}"),
        parameters={"skill": skill},
        parent_candidate_id=parent,
        evidence_refs=(f"proposal:{cid}",),
    )


def _manifest(
    *,
    traffic: TrafficMode = TrafficMode.OFFLINE,
    min_samples: int = 1,
    allowed_data_classes: tuple[str, ...] = ("public",),
) -> ExperimentManifest:
    return ExperimentManifest(
        experiment_id="exp.mirror.v1",
        hypothesis="Bounded sandbox learning improves quality without safety regression.",
        owner="p1-learning",
        source_commit="a" * 40,
        environment_id="mirror.offline",
        candidate_ref="candidate:mirror.v1",
        eligibility=ExperimentEligibility(
            traffic_mode=traffic,
            max_traffic_fraction=0.0 if traffic is TrafficMode.OFFLINE else 0.1,
            allowed_data_classes=allowed_data_classes,
            tenant_ids=() if traffic is TrafficMode.OFFLINE else ("tenant-test",),
            external_side_effects_allowed=False,
        ),
        budget=ExperimentBudget(
            max_samples=128,
            max_tokens=50_000,
            max_cost_units=10.0,
            max_wall_time_s=3600.0,
        ),
        metrics=(
            ExperimentMetric(
                metric_id="quality.acceptance",
                direction=MetricDirection.MAXIMIZE,
                minimum_samples=min_samples,
                source="independent-eval",
            ),
            ExperimentMetric(
                metric_id="safety.score",
                direction=MetricDirection.MAXIMIZE,
                minimum_samples=min_samples,
                source="independent-safety-eval",
            ),
        ),
        parent_experiment_id=None,
        tags=("mirror-room", "learning"),
    )


def _spec(
    *,
    manifest: ExperimentManifest | None = None,
    max_episodes: int = 64,
    stagnation_patience: int = 2,
) -> MirrorRoomSpec:
    return MirrorRoomSpec(
        manifest=manifest or _manifest(),
        production_baseline=_candidate("production-v1", 0.2, producer="release"),
        metrics=(
            MirrorMetricPolicy(
                metric_id="quality.acceptance",
                direction=MetricDirection.MAXIMIZE,
                minimum_improvement=0.01,
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
            max_steps_per_episode=8,
            max_tokens_per_episode=64,
            max_cost_units_per_episode=0.1,
        ),
        budget=MirrorBudget(
            max_generations=3,
            max_candidates_per_generation=2,
            max_episodes=max_episodes,
            max_total_steps=512,
            max_total_tokens=4096,
            max_total_cost_units=5.0,
        ),
        hard_example_limit=2,
        stagnation_patience=stagnation_patience,
    )


def _scenarios(count: int = 1):
    return tuple(
        MirrorScenario(
            scenario_id=f"{split.value}-{index}",
            split=split,
            payload={"difficulty": index / 20.0, "secret": f"{split.value}-{index}"},
            tags=(split.value,),
        )
        for split in ScenarioSplit
        for index in range(count)
    )


class Executor:
    executor_id = "executor-v1"

    def __init__(self, *, unsafe: bool = False, holdout_penalty: float = 0.0, diverge: bool = False):
        self.unsafe = unsafe
        self.holdout_penalty = holdout_penalty
        self.diverge = diverge
        self.calls: list[tuple[str, str, int]] = []
        self.counter = 0

    def execute(self, *, candidate, scenario, seed, policy):
        self.counter += 1
        self.calls.append((candidate.candidate_id, scenario.scenario_id, seed))
        skill = float(candidate.parameters["skill"])
        quality = 0.5 + skill - float(scenario.payload["difficulty"])
        if scenario.split is ScenarioSplit.HOLDOUT and candidate.parent_candidate_id:
            quality -= self.holdout_penalty
        quality = min(1.0, max(0.0, quality))
        salt = self.counter if self.diverge else 0
        return EpisodeOutcome(
            metric_values={"quality.acceptance": quality, "safety.score": 0.95},
            observation_digest=_sha(f"{candidate.digest}:{scenario.digest}:{seed}:{salt}"),
            steps=1,
            tokens=8,
            cost_units=0.01,
            capabilities_used=("network",) if self.unsafe else ("compute",),
        )


class Generator:
    generator_id = "learner"

    def __init__(self, step: float = 0.1):
        self.step = step
        self.feedback = []

    def propose(self, feedback, *, limit):
        self.feedback.append(feedback)
        skill = float(feedback.champion.parameters["skill"])
        return (
            _candidate(
                f"candidate-{feedback.generation}",
                skill + self.step,
                parent=feedback.champion.candidate_id,
            ),
        )[:limit]


def _run(*, executor: Executor | None = None, generations: int = 2, spec: MirrorRoomSpec | None = None):
    room_spec = spec or _spec()
    generator = Generator()
    actual_executor = executor or Executor()
    receipt = MirrorRoom(room_spec, actual_executor).learn(
        run_id="run-1",
        generator=generator,
        scenarios=_scenarios(),
        generations=generations,
    )
    return room_spec, actual_executor, generator, receipt


def test_requires_offline_zero_traffic_manifest() -> None:
    with pytest.raises(MirrorRoomError, match="offline"):
        _spec(manifest=_manifest(traffic=TrafficMode.SHADOW))


def test_candidate_cannot_claim_production_authority() -> None:
    with pytest.raises(MirrorRoomError, match="production authority"):
        MirrorCandidate(
            candidate_id="bad",
            version="v-bad",
            producer_id="learner",
            change_ref="change:bad",
            change_digest=_sha("bad"),
            parameters={},
            production_authority=True,
        )


def test_generator_observes_train_split_only() -> None:
    _, _, generator, _ = _run(generations=2)
    assert len(generator.feedback) == 2
    assert all(
        scenario.split is ScenarioSplit.TRAIN
        for feedback in generator.feedback
        for scenario in feedback.training_scenarios
    )
    assert all(
        item.scenario_id.startswith("train-")
        for feedback in generator.feedback[1:]
        for item in feedback.hard_examples
    )


def test_iterative_validation_champion_and_sealed_holdout() -> None:
    spec, executor, _, receipt = _run(generations=2)
    assert receipt.final_sandbox_champion.candidate_id == "candidate-2"
    assert receipt.final_sandbox_champion != spec.production_baseline
    assert receipt.holdout_report is not None and receipt.holdout_report.passed
    holdout_calls = [call for call in executor.calls if call[1].startswith("holdout-")]
    assert [call[0] for call in holdout_calls] == ["production-v1", "candidate-2"]
    assert receipt.eligible_for_external_promotion is True
    assert receipt.production_authority is False
    assert receipt.direct_self_modify is False


def test_paired_comparison_uses_same_seed() -> None:
    _, executor, _, _ = _run(generations=1)
    validation = [call for call in executor.calls if call[1] == "validation-0"]
    assert len(validation) == 2
    assert validation[0][2] == validation[1][2]


def test_sealed_holdout_can_veto_validation_winner() -> None:
    _, _, _, receipt = _run(executor=Executor(holdout_penalty=0.8), generations=1)
    assert receipt.final_sandbox_champion.candidate_id == "candidate-1"
    assert receipt.holdout_report is not None
    assert receipt.holdout_report.passed is False
    assert receipt.eligible_for_external_promotion is False


def test_forbidden_capability_fails_closed() -> None:
    with pytest.raises(MirrorRoomError, match="forbidden capabilities"):
        _run(executor=Executor(unsafe=True), generations=1)


def test_whole_run_episode_budget_fails_closed() -> None:
    with pytest.raises(MirrorRoomError, match="episode budget exhausted"):
        _run(spec=_spec(max_episodes=3), generations=1)


def test_replay_detects_nondeterministic_executor() -> None:
    spec = _spec()
    sandbox = MirrorSandbox(spec, Executor(diverge=True))
    scenario = next(s for s in _scenarios() if s.split is ScenarioSplit.TRAIN)
    receipt = sandbox.run_episode(
        run_id="replay-run",
        candidate=spec.production_baseline,
        scenario=scenario,
    )
    with pytest.raises(MirrorRoomError, match="replay diverged"):
        sandbox.verify_replay(receipt, candidate=spec.production_baseline, scenario=scenario)


def test_promotion_handoff_requires_independent_evidence_and_rollback() -> None:
    _, _, _, receipt = _run(generations=1)
    with pytest.raises(MirrorRoomError, match="producer cannot independently verify"):
        qualify_for_external_promotion(
            receipt,
            verifier_id="learner",
            evaluation_refs=("eval:quality", "eval:safety"),
            verified_at=10,
        )
    evidence = qualify_for_external_promotion(
        receipt,
        verifier_id="independent-verifier",
        evaluation_refs=("eval:quality", "eval:safety"),
        verified_at=10,
    )
    assert evidence.production_authority is False
    assert evidence.rollback_candidate_id == receipt.production_baseline.candidate_id
    assert evidence.candidate_id == receipt.final_sandbox_champion.candidate_id
    assert evidence.evidence_ref().category == "mirror_room_promotion_evidence"


def test_promotion_handoff_rejects_single_evidence_channel() -> None:
    _, _, _, receipt = _run(generations=1)
    with pytest.raises(MirrorRoomError, match="at least two"):
        qualify_for_external_promotion(
            receipt,
            verifier_id="independent-verifier",
            evaluation_refs=("eval:only",),
            verified_at=10,
        )


def test_minimum_sample_contract_is_enforced() -> None:
    spec = _spec(manifest=_manifest(min_samples=2))
    with pytest.raises(MirrorRoomError, match="validation split"):
        _run(spec=spec, generations=1)


def test_scenario_payload_is_copied_at_boundary() -> None:
    payload = {"nested": {"value": 1}}
    scenario = MirrorScenario("train-copy", ScenarioSplit.TRAIN, payload)
    payload["nested"]["value"] = 2
    assert scenario.payload["nested"]["value"] == 1


def test_deterministic_components_produce_deterministic_run_digest() -> None:
    first = _run(generations=2)[3]
    second = _run(generations=2)[3]
    assert first.digest == second.digest


def test_source_and_ai_mirror_room_are_byte_identical() -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton" / "learning" / "mirror_room"
    mirror = root / "skeleton" / "ai" / "learning" / "mirror_room"
    names = (
        "__init__.py",
        "adaptation.py",
        "contracts.py",
        "memory.py",
        "sandbox.py",
        "evaluation.py",
        "engine.py",
        "promotion.py",
        "replay.py",
    )
    assert all((source / name).read_bytes() == (mirror / name).read_bytes() for name in names)


def test_evidence_payloads_are_structurally_immutable() -> None:
    nested = {"nested": {"value": 1}}
    scenario = MirrorScenario("train-immutable", ScenarioSplit.TRAIN, nested)
    candidate = _candidate("immutable-candidate", 0.4)
    outcome = EpisodeOutcome(
        metric_values={"quality.acceptance": 0.7, "safety.score": 0.9},
        observation_digest=_sha("immutable-outcome"),
        steps=1,
        tokens=1,
        cost_units=0.01,
    )

    with pytest.raises(TypeError):
        scenario.payload["nested"]["value"] = 2
    with pytest.raises(TypeError):
        candidate.parameters["skill"] = 0.9
    with pytest.raises(TypeError):
        outcome.metric_values["quality.acceptance"] = 0.1

def test_duplicate_payload_cannot_cross_learning_splits() -> None:
    duplicate = {"difficulty": 0.1, "secret": "same"}
    scenarios = (
        MirrorScenario("train-dup", ScenarioSplit.TRAIN, duplicate),
        MirrorScenario("validation-dup", ScenarioSplit.VALIDATION, {"difficulty": 0.2}),
        MirrorScenario("holdout-dup", ScenarioSplit.HOLDOUT, duplicate),
    )
    room = MirrorRoom(_spec(), Executor())
    with pytest.raises(MirrorRoomError, match="split contamination|duplicate scenario payload"):
        room.learn(
            run_id="dup-run",
            generator=Generator(),
            scenarios=scenarios,
            generations=1,
        )


def test_non_public_scenario_requires_governance_authorization() -> None:
    with pytest.raises(MirrorRoomError, match="learning authorization receipt"):
        MirrorScenario(
            "train-private",
            ScenarioSplit.TRAIN,
            {"difficulty": 0.1},
            data_class="internal",
        )


def test_scenario_data_class_cannot_exceed_experiment_eligibility() -> None:
    scenarios = (
        MirrorScenario(
            "train-private",
            ScenarioSplit.TRAIN,
            {"difficulty": 0.1},
            data_class="internal",
            authorization_ref="gov:training:1",
        ),
        MirrorScenario("validation-public", ScenarioSplit.VALIDATION, {"difficulty": 0.2}),
        MirrorScenario("holdout-public", ScenarioSplit.HOLDOUT, {"difficulty": 0.3}),
    )
    with pytest.raises(MirrorRoomError, match="eligibility ceiling"):
        MirrorRoom(_spec(), Executor()).learn(
            run_id="privacy-run",
            generator=Generator(),
            scenarios=scenarios,
            generations=1,
        )


def test_declared_non_public_training_data_is_admitted_with_receipt() -> None:
    manifest = _manifest(allowed_data_classes=("public", "internal"))
    spec = _spec(manifest=manifest)
    scenarios = (
        MirrorScenario(
            "train-private",
            ScenarioSplit.TRAIN,
            {"difficulty": 0.1},
            data_class="internal",
            authorization_ref="gov:training:1",
            source_ref="fixture-private",
        ),
        MirrorScenario("validation-public", ScenarioSplit.VALIDATION, {"difficulty": 0.2}),
        MirrorScenario("holdout-public", ScenarioSplit.HOLDOUT, {"difficulty": 0.3}),
    )
    receipt = MirrorRoom(spec, Executor()).learn(
        run_id="privacy-allowed",
        generator=Generator(),
        scenarios=scenarios,
        generations=1,
    )
    assert receipt.generations


def test_generator_cannot_also_be_sandbox_evaluator() -> None:
    class CollidingExecutor(Executor):
        executor_id = "learner"

    with pytest.raises(MirrorRoomError, match="must be independent"):
        _run(executor=CollidingExecutor(), generations=1)


class FailureShiftExecutor(Executor):
    def execute(self, *, candidate, scenario, seed, policy):
        result = super().execute(
            candidate=candidate,
            scenario=scenario,
            seed=seed,
            policy=policy,
        )
        values = dict(result.metric_values)
        if candidate.candidate_id == "candidate-1" and scenario.scenario_id == "train-0":
            values["quality.acceptance"] = 0.0
        if candidate.candidate_id == "candidate-2" and scenario.scenario_id == "train-1":
            values["quality.acceptance"] = 0.0
        return EpisodeOutcome(
            metric_values=values,
            observation_digest=_sha(
                f"shift:{candidate.digest}:{scenario.digest}:{seed}:{values['quality.acceptance']}"
            ),
            steps=result.steps,
            tokens=result.tokens,
            cost_units=result.cost_units,
            capabilities_used=result.capabilities_used,
            evidence_refs=result.evidence_refs,
        )


def test_hard_example_memory_accumulates_and_prioritizes_curriculum() -> None:
    spec = _spec()
    generator = Generator(step=0.2)
    receipt = MirrorRoom(spec, FailureShiftExecutor()).learn(
        run_id="hard-memory",
        generator=generator,
        scenarios=_scenarios(count=3),
        generations=2,
    )
    assert len(generator.feedback) == 2
    assert generator.feedback[1].training_scenarios[0].scenario_id == "train-0"
    final_hard = {item.scenario_id for item in receipt.generations[-1].hard_examples}
    assert "train-0" in final_hard
    assert "train-1" in final_hard


class VariableDeltaExecutor(Executor):
    def execute(self, *, candidate, scenario, seed, policy):
        result = super().execute(
            candidate=candidate,
            scenario=scenario,
            seed=seed,
            policy=policy,
        )
        values = dict(result.metric_values)
        if candidate.parent_candidate_id and scenario.split is ScenarioSplit.VALIDATION:
            index = int(scenario.scenario_id.rsplit("-", 1)[1])
            values["quality.acceptance"] = min(
                1.0,
                max(0.0, values["quality.acceptance"] + (0.12 if index % 2 == 0 else -0.08)),
            )
        return EpisodeOutcome(
            metric_values=values,
            observation_digest=_sha(
                f"var:{candidate.digest}:{scenario.digest}:{seed}:{values['quality.acceptance']}"
            ),
            steps=result.steps,
            tokens=result.tokens,
            cost_units=result.cost_units,
            capabilities_used=result.capabilities_used,
            evidence_refs=result.evidence_refs,
        )


def test_validation_confidence_is_corrected_for_candidate_search_family() -> None:
    from skeleton.learning.mirror_room.evaluation import PairedEvaluator

    spec = _spec(manifest=_manifest(min_samples=4))
    scenarios = tuple(
        item for item in _scenarios(count=4)
        if item.split is ScenarioSplit.VALIDATION
    )
    baseline = spec.production_baseline
    candidate = _candidate("family-candidate", 0.3, parent=baseline.candidate_id)

    narrow = PairedEvaluator(
        spec,
        MirrorSandbox(spec, VariableDeltaExecutor()),
    ).compare(
        run_id="family-narrow",
        baseline=baseline,
        candidate=candidate,
        scenarios=scenarios,
        split=ScenarioSplit.VALIDATION,
        comparison_family_size=1,
    )
    wide = PairedEvaluator(
        spec,
        MirrorSandbox(spec, VariableDeltaExecutor()),
    ).compare(
        run_id="family-wide",
        baseline=baseline,
        candidate=candidate,
        scenarios=scenarios,
        split=ScenarioSplit.VALIDATION,
        comparison_family_size=12,
    )
    narrow_metric = next(
        item for item in narrow.metric_comparisons
        if item.metric_id == "quality.acceptance"
    )
    wide_metric = next(
        item for item in wide.metric_comparisons
        if item.metric_id == "quality.acceptance"
    )
    assert wide_metric.adjusted_confidence_level > narrow_metric.adjusted_confidence_level
    assert wide_metric.lower_confidence_bound <= narrow_metric.lower_confidence_bound
    assert wide_metric.comparison_family_size == 12


def test_run_receipt_binds_generator_and_evaluator_identity() -> None:
    _, executor, generator, receipt = _run(generations=1)
    assert receipt.generator_id == generator.generator_id
    assert receipt.executor_id == executor.executor_id
    assert receipt.generator_id != receipt.executor_id


def test_selected_lineage_replay_reexecutes_exact_evidence() -> None:
    spec, _, _, receipt = _run(generations=2)
    replay = verify_selected_lineage(
        receipt,
        spec=spec,
        executor=Executor(),
        scenarios=_scenarios(),
    )
    assert replay.exact_match is True
    assert replay.episodes_replayed > 0
    assert replay.episode_digests == replay.replayed_episode_digests
    assert replay.production_authority is False


def test_selected_lineage_replay_detects_executor_divergence() -> None:
    spec, _, _, receipt = _run(generations=1)
    with pytest.raises(MirrorRoomError, match="replay diverged"):
        verify_selected_lineage(
            receipt,
            spec=spec,
            executor=Executor(diverge=True),
            scenarios=_scenarios(),
        )


def test_selected_lineage_replay_rejects_changed_holdout() -> None:
    spec, _, _, receipt = _run(generations=1)
    changed = list(_scenarios())
    changed[-1] = MirrorScenario(
        changed[-1].scenario_id,
        ScenarioSplit.HOLDOUT,
        {"difficulty": 0.99, "secret": "changed"},
        tags=("holdout",),
    )
    with pytest.raises(MirrorRoomError, match="sealed holdout identity changed"):
        verify_selected_lineage(
            receipt,
            spec=spec,
            executor=Executor(),
            scenarios=tuple(changed),
        )


def test_promotion_verifier_must_be_independent_of_sandbox_evaluator() -> None:
    _, executor, _, receipt = _run(generations=1)
    with pytest.raises(MirrorRoomError, match="independent of generator and executor|sandbox evaluator"):
        qualify_for_external_promotion(
            receipt,
            verifier_id=executor.executor_id,
            evaluation_refs=("eval:quality", "eval:safety"),
            verified_at=10,
        )

class ValidationBlindExecutor(Executor):
    def execute(self, *, candidate, scenario, seed, policy):
        result = super().execute(
            candidate=candidate,
            scenario=scenario,
            seed=seed,
            policy=policy,
        )
        values = dict(result.metric_values)
        if (
            candidate.candidate_id == "candidate-1"
            and scenario.split is ScenarioSplit.VALIDATION
        ):
            values["quality.acceptance"] = 0.0
        return EpisodeOutcome(
            metric_values=values,
            observation_digest=_sha(
                f"blind:{candidate.digest}:{scenario.digest}:{seed}:"
                f"{values['quality.acceptance']}"
            ),
            steps=result.steps,
            tokens=result.tokens,
            cost_units=result.cost_units,
            capabilities_used=result.capabilities_used,
            evidence_refs=result.evidence_refs,
        )


def test_validation_selection_is_blind_to_candidate_generator() -> None:
    spec = _spec()
    generator = Generator(step=0.1)
    executor = ValidationBlindExecutor()
    receipt = MirrorRoom(spec, executor).learn(
        run_id="blind-validation",
        generator=generator,
        scenarios=_scenarios(),
        generations=2,
    )

    assert generator.feedback[1].champion.candidate_id == "candidate-1"
    assert receipt.generations[0].learning_champion_id == "candidate-1"
    assert receipt.generations[0].selected_champion_id == "production-v1"

    validation_two = [
        call[0]
        for call in executor.calls
        if call[1] == "validation-0"
    ]
    assert validation_two[-2:] == ["production-v1", "candidate-2"]
    assert receipt.final_sandbox_champion.candidate_id == "candidate-2"


def test_validation_qualification_never_changes_training_parent_lineage() -> None:
    spec = _spec()
    generator = Generator(step=0.1)
    receipt = MirrorRoom(spec, Executor()).learn(
        run_id="dual-champion",
        generator=generator,
        scenarios=_scenarios(),
        generations=2,
    )
    first, second = receipt.generations
    assert first.learning_champion_id == "candidate-1"
    assert second.incoming_champion_id == "candidate-1"
    assert generator.feedback[1].champion.candidate_id == "candidate-1"
    assert receipt.final_sandbox_champion.candidate_id == "candidate-2"

def test_behaviorally_duplicate_candidate_is_rejected() -> None:
    class NoOpGenerator:
        generator_id = "learner"

        def propose(self, feedback, *, limit):
            champion = feedback.champion
            return (
                MirrorCandidate(
                    candidate_id="cosmetic-change",
                    version="version-cosmetic-change",
                    producer_id=self.generator_id,
                    change_ref="change:cosmetic-change",
                    change_digest=champion.change_digest,
                    parameters=dict(champion.parameters),
                    parent_candidate_id=champion.candidate_id,
                    evidence_refs=("proposal:cosmetic-change",),
                ),
            )

    with pytest.raises(MirrorRoomError, match="behavior was already explored"):
        MirrorRoom(_spec(), Executor()).learn(
            run_id="no-op-learning",
            generator=NoOpGenerator(),
            scenarios=_scenarios(),
            generations=1,
        )


def test_candidate_behavior_digest_ignores_cosmetic_identity_fields() -> None:
    shared_change = _sha("shared-behavior-artifact")
    left = MirrorCandidate(
        candidate_id="behavior-left",
        version="version-left",
        producer_id="learner",
        change_ref="change:left",
        change_digest=shared_change,
        parameters={"skill": 0.4},
        parent_candidate_id="production-v1",
        evidence_refs=("proposal:left",),
    )
    right = MirrorCandidate(
        candidate_id="behavior-right",
        version="version-right",
        producer_id="learner",
        change_ref="change:right",
        change_digest=shared_change,
        parameters={"skill": 0.4},
        parent_candidate_id="production-v1",
        evidence_refs=("proposal:right",),
    )
    assert left.digest != right.digest
    assert left.behavior_digest == right.behavior_digest


def test_change_artifact_participates_in_behavior_identity() -> None:
    left = MirrorCandidate(
        candidate_id="artifact-left",
        version="artifact-left",
        producer_id="learner",
        change_ref="change:artifact-left",
        change_digest=_sha("artifact-a"),
        parameters={"skill": 0.4},
        parent_candidate_id="production-v1",
    )
    right = MirrorCandidate(
        candidate_id="artifact-right",
        version="artifact-right",
        producer_id="learner",
        change_ref="change:artifact-right",
        change_digest=_sha("artifact-b"),
        parameters={"skill": 0.4},
        parent_candidate_id="production-v1",
    )
    assert left.behavior_digest != right.behavior_digest


def test_stagnation_patience_stops_unproductive_search() -> None:
    class RegressingGenerator:
        generator_id = "learner"

        def __init__(self):
            self.calls = 0

        def propose(self, feedback, *, limit):
            self.calls += 1
            return (
                _candidate(
                    f"regression-{self.calls}",
                    0.2 - (self.calls * 0.05),
                    parent=feedback.champion.candidate_id,
                ),
            )

    generator = RegressingGenerator()
    receipt = MirrorRoom(
        _spec(stagnation_patience=2),
        Executor(),
    ).learn(
        run_id="stagnation",
        generator=generator,
        scenarios=_scenarios(),
        generations=3,
    )

    assert generator.calls == 2
    assert len(receipt.generations) == 2
    assert all(
        row.learning_champion_id == "production-v1"
        for row in receipt.generations
    )


def test_stagnation_patience_is_bounded_by_generation_budget() -> None:
    with pytest.raises(MirrorRoomError, match="cannot exceed generation budget"):
        _spec(stagnation_patience=4)

def _coordinate_learner() -> DeterministicCoordinateLearner:
    return DeterministicCoordinateLearner(
        generator_id="coordinate-learner",
        dimensions=(
            NumericDimension(
                name="skill",
                lower=0.0,
                upper=0.9,
                initial_step=0.2,
                min_step=0.025,
            ),
        ),
    )


def test_coordinate_learner_improves_without_custom_generator() -> None:
    spec = _spec()
    receipt = MirrorRoom(spec, Executor()).learn(
        run_id="coordinate-learning",
        generator=_coordinate_learner(),
        scenarios=_scenarios(),
        generations=2,
    )

    assert receipt.final_sandbox_champion.candidate_id != "production-v1"
    assert (
        float(receipt.final_sandbox_champion.parameters["skill"])
        > float(spec.production_baseline.parameters["skill"])
    )
    assert receipt.eligible_for_external_promotion is True


def test_coordinate_learner_is_deterministic_for_same_run() -> None:
    spec = _spec()
    first = MirrorRoom(spec, Executor()).learn(
        run_id="coordinate-deterministic",
        generator=_coordinate_learner(),
        scenarios=_scenarios(),
        generations=2,
    )
    second = MirrorRoom(spec, Executor()).learn(
        run_id="coordinate-deterministic",
        generator=_coordinate_learner(),
        scenarios=_scenarios(),
        generations=2,
    )
    assert first.digest == second.digest


def test_coordinate_learner_adapts_step_after_train_selection() -> None:
    learner = _coordinate_learner()
    spec = _spec()
    room = MirrorRoom(spec, Executor())
    receipt = room.learn(
        run_id="coordinate-step",
        generator=learner,
        scenarios=_scenarios(),
        generations=2,
    )

    assert len(receipt.generations) == 2
    assert learner.step_sizes["skill"] > 0.2


def test_coordinate_learner_rejects_undeclared_numeric_surface() -> None:
    learner = DeterministicCoordinateLearner(
        generator_id="coordinate-learner",
        dimensions=(
            NumericDimension(
                name="missing",
                lower=0.0,
                upper=1.0,
                initial_step=0.1,
            ),
        ),
    )
    with pytest.raises(MirrorRoomError, match="not numeric"):
        MirrorRoom(_spec(), Executor()).learn(
            run_id="coordinate-missing",
            generator=learner,
            scenarios=_scenarios(),
            generations=1,
        )

def test_training_archive_contains_train_only_evidence() -> None:
    _, _, _, receipt = _run(generations=2)
    archive = TrainingLearningArchive.from_runs((receipt,))

    assert len(archive.lessons) == 2
    selected_train_digests = {
        evaluation.training_report.digest
        for generation in receipt.generations
        for evaluation in generation.evaluations
        if evaluation.selected_for_learning
    }
    assert {
        lesson.training_report_digest
        for lesson in archive.lessons
    } == selected_train_digests

    payload = archive.payload()
    assert payload["evidence_plane"] == "train"
    assert payload["contains_validation_evidence"] is False
    assert payload["contains_holdout_evidence"] is False
    assert all(
        lesson["evidence_plane"] == "train"
        for lesson in payload["lessons"]
    )


def test_training_archive_tracks_train_selection_even_if_validation_rejects() -> None:
    spec = _spec()
    receipt = MirrorRoom(spec, ValidationBlindExecutor()).learn(
        run_id="archive-blind",
        generator=Generator(step=0.1),
        scenarios=_scenarios(),
        generations=2,
    )
    archive = TrainingLearningArchive.from_runs((receipt,))

    assert archive.lessons[0].candidate_id == "candidate-1"
    assert receipt.generations[0].selected_champion_id == "production-v1"
    assert archive.lessons[0].training_utility_delta > 0.0


def test_training_archive_is_deterministic_and_scopeable() -> None:
    _, _, _, receipt = _run(generations=2)
    left = TrainingLearningArchive.from_runs((receipt,))
    right = TrainingLearningArchive.from_runs((receipt,))

    assert left.digest == right.digest
    assert left.for_experiment(receipt.experiment_id).digest == left.digest
    assert TrainingLearningArchive().for_experiment(
        receipt.experiment_id
    ).lessons == ()


def test_coordinate_learner_warm_starts_from_train_archive() -> None:
    _, _, _, receipt = _run(generations=2)
    archive = TrainingLearningArchive.from_runs((receipt,)).for_experiment(
        receipt.experiment_id
    )
    learner = DeterministicCoordinateLearner(
        generator_id="archive-learner",
        dimensions=(
            NumericDimension(
                name="skill",
                lower=0.0,
                upper=1.0,
                initial_step=0.01,
                min_step=0.001,
            ),
        ),
        training_archive=archive,
    )

    assert learner.step_sizes["skill"] == pytest.approx(0.1)
    assert archive.preferred_direction("skill") == 1
    assert archive.dimension_strength("skill") > 0.0


def test_coordinate_learner_archive_changes_strategy_identity() -> None:
    _, _, _, receipt = _run(generations=1)
    archive = TrainingLearningArchive.from_runs((receipt,))
    dimension = NumericDimension(
        name="skill",
        lower=0.0,
        upper=1.0,
        initial_step=0.05,
    )
    cold = DeterministicCoordinateLearner(
        generator_id="archive-identity",
        dimensions=(dimension,),
    )
    warm = DeterministicCoordinateLearner(
        generator_id="archive-identity",
        dimensions=(dimension,),
        training_archive=archive,
    )

    assert cold.strategy_digest != warm.strategy_digest


def test_near_duplicate_cross_split_corpus_is_detectable_before_learning() -> None:
    train = MirrorScenario(
        "train-near-duplicate",
        ScenarioSplit.TRAIN,
        {"text": "alpha beta gamma delta epsilon zeta eta theta iota kappa"},
    )
    validation = MirrorScenario(
        "validation-near-duplicate",
        ScenarioSplit.VALIDATION,
        {"text": "alpha beta gamma delta epsilon zeta eta theta iota lambda"},
    )
    holdout = MirrorScenario(
        "holdout-independent",
        ScenarioSplit.HOLDOUT,
        {"text": "omega psi chi phi upsilon tau sigma rho independent sample"},
    )
    report = inspect_split_integrity(
        (train, validation, holdout),
        policy=SplitIntegrityPolicy(
            near_duplicate_threshold=0.5,
            minimum_tokens_for_similarity=4,
            shingle_size=2,
        ),
    )
    assert report.passed is False
    assert report.suspicious_pairs
    assert report.maximum_cross_split_similarity >= 0.5


def test_curriculum_is_training_only_deterministic_and_hard_example_weighted() -> None:
    scenarios = (
        MirrorScenario("train-easy", ScenarioSplit.TRAIN, {"x": 1}, tags=("math",)),
        MirrorScenario("train-hard", ScenarioSplit.TRAIN, {"x": 2}, tags=("logic",)),
        MirrorScenario("train-other", ScenarioSplit.TRAIN, {"x": 3}, tags=("math",)),
    )
    hard = (
        HardExample(
            scenario_id="train-hard",
            scenario_digest=scenarios[1].digest,
            difficulty=1.5,
            metric_deltas={"quality.acceptance": -0.4},
        ),
    )
    policy = CurriculumPolicy(interleave_primary_tags=False)
    first = build_curriculum(scenarios, hard, policy=policy)
    second = build_curriculum(scenarios, hard, policy=policy)

    assert first.digest == second.digest
    assert first.scenarios[0].scenario_id == "train-hard"
    assert all(item.split is ScenarioSplit.TRAIN for item in first.scenarios)


def test_validation_candidate_search_budget_fails_closed() -> None:
    base = _spec()
    constrained = MirrorRoomSpec(
        manifest=base.manifest,
        production_baseline=base.production_baseline,
        metrics=base.metrics,
        sandbox_policy=base.sandbox_policy,
        budget=MirrorBudget(
            max_generations=3,
            max_candidates_per_generation=2,
            max_episodes=64,
            max_total_steps=512,
            max_total_tokens=4096,
            max_total_cost_units=5.0,
            max_validation_candidate_evaluations=1,
        ),
        hard_example_limit=base.hard_example_limit,
        stagnation_patience=base.stagnation_patience,
    )

    class TwoCandidateGenerator:
        generator_id = "learner"

        def propose(self, feedback, *, limit):
            skill = float(feedback.champion.parameters["skill"])
            return (
                _candidate(
                    "selection-budget-a",
                    skill + 0.10,
                    parent=feedback.champion.candidate_id,
                ),
                _candidate(
                    "selection-budget-b",
                    skill + 0.20,
                    parent=feedback.champion.candidate_id,
                ),
            )[:limit]

    with pytest.raises(MirrorRoomError, match="validation selection budget"):
        MirrorRoom(constrained, Executor()).learn(
            run_id="selection-budget",
            generator=TwoCandidateGenerator(),
            scenarios=_scenarios(),
            generations=1,
        )


def test_run_and_promotion_bind_split_integrity_and_sealed_holdout() -> None:
    _, _, _, receipt = _run(generations=1)
    assert len(receipt.split_integrity_digest) == 64
    assert receipt.validation_candidate_evaluations == 1

    evidence = qualify_for_external_promotion(
        receipt,
        verifier_id="independent-verifier",
        evaluation_refs=("eval:quality", "eval:safety"),
        verified_at=10,
    )

    assert evidence.sealed_holdout_digest == receipt.sealed_holdout_digest
    assert evidence.split_integrity_digest == receipt.split_integrity_digest
    assert evidence.generator_id == receipt.generator_id
    assert evidence.executor_id == receipt.executor_id


def test_worst_case_guardrail_blocks_locally_unsafe_candidate() -> None:
    class LocalizedSafetyRegressionExecutor(Executor):
        def execute(self, *, candidate, scenario, seed, policy):
            outcome = super().execute(
                candidate=candidate,
                scenario=scenario,
                seed=seed,
                policy=policy,
            )
            safety = 0.90
            if candidate.parent_candidate_id is not None:
                if scenario.scenario_id.endswith("-1"):
                    safety = 1.00
                elif scenario.scenario_id.endswith("-2"):
                    safety = 0.80
            return EpisodeOutcome(
                metric_values={
                    "quality.acceptance": outcome.metric_values["quality.acceptance"],
                    "safety.score": safety,
                },
                observation_digest=_sha(
                    f"{outcome.observation_digest}:localized-safety:{safety}"
                ),
                steps=outcome.steps,
                tokens=outcome.tokens,
                cost_units=outcome.cost_units,
                capabilities_used=outcome.capabilities_used,
                evidence_refs=outcome.evidence_refs,
            )

    spec = _spec()
    receipt = MirrorRoom(spec, LocalizedSafetyRegressionExecutor()).learn(
        run_id="localized-safety-regression",
        generator=Generator(step=0.2),
        scenarios=_scenarios(count=3),
        generations=1,
    )

    evaluation = receipt.generations[0].evaluations[0]
    safety = next(
        item
        for item in evaluation.validation_report.metric_comparisons
        if item.metric_id == "safety.score"
    )
    assert safety.oriented_delta == pytest.approx(0.0)
    assert safety.worst_case_delta == pytest.approx(-0.1)
    assert safety.passed is False
    assert receipt.final_sandbox_champion == spec.production_baseline

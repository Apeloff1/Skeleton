"""Iterative Mirror Room learning engine.

The engine supports bounded multi-generation adaptation while preserving a
frozen production baseline and a sealed final holdout.  Sandbox champions may
change between generations; production behavior never changes here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

from .contracts import (
    HardExample,
    LearningFeedback,
    MirrorCandidate,
    MirrorRoomError,
    MirrorRoomSpec,
    MirrorScenario,
    ScenarioSplit,
    _digest,
    _sha256,
)
from .curriculum import build_curriculum
from .evaluation import ComparisonReport, PairedEvaluator
from .integrity import validate_split_integrity
from .sandbox import MirrorSandbox, SandboxExecutor, SandboxUsage


@runtime_checkable
class CandidateGenerator(Protocol):
    """A bounded candidate proposer.

    The only scenario payloads it receives are TRAIN scenarios.  Validation
    and holdout material is intentionally absent from this interface.
    """

    generator_id: str

    def propose(
        self,
        feedback: LearningFeedback,
        *,
        limit: int,
    ) -> Sequence[MirrorCandidate]: ...


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    candidate: MirrorCandidate
    training_report: ComparisonReport
    validation_report: ComparisonReport
    selected_for_learning: bool
    selected: bool

    @property
    def digest(self) -> str:
        return _digest(
            {
                "candidate_digest": self.candidate.digest,
                "training_report": self.training_report.digest,
                "validation_report": self.validation_report.digest,
                "selected_for_learning": self.selected_for_learning,
                "selected": self.selected,
            }
        )


@dataclass(frozen=True, slots=True)
class GenerationRecord:
    generation: int
    incoming_champion_id: str
    evaluations: tuple[CandidateEvaluation, ...]
    learning_champion_id: str
    selected_champion_id: str
    hard_examples: tuple[HardExample, ...]
    curriculum_digest: str

    @property
    def digest(self) -> str:
        return _digest(
            {
                "generation": self.generation,
                "incoming_champion_id": self.incoming_champion_id,
                "evaluations": [item.digest for item in self.evaluations],
                "learning_champion_id": self.learning_champion_id,
                "selected_champion_id": self.selected_champion_id,
                "curriculum_digest": self.curriculum_digest,
                "hard_examples": [
                    {
                        "scenario_id": item.scenario_id,
                        "scenario_digest": item.scenario_digest,
                        "difficulty": item.difficulty,
                        "metric_deltas": dict(item.metric_deltas),
                    }
                    for item in self.hard_examples
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class MirrorRunReceipt:
    """Immutable result of a complete bounded learning run."""

    run_id: str
    experiment_id: str
    spec_digest: str
    manifest_digest: str
    generator_id: str
    executor_id: str
    production_baseline: MirrorCandidate
    final_sandbox_champion: MirrorCandidate
    generations: tuple[GenerationRecord, ...]
    holdout_report: ComparisonReport | None
    sealed_holdout_digest: str
    split_integrity_digest: str
    validation_candidate_evaluations: int
    usage: SandboxUsage
    eligible_for_external_promotion: bool
    production_authority: bool = False
    direct_self_modify: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.generator_id, str) or not self.generator_id.strip():
            raise MirrorRoomError("Mirror Run requires generator identity")
        if not isinstance(self.executor_id, str) or not self.executor_id.strip():
            raise MirrorRoomError("Mirror Run requires executor identity")
        if self.generator_id == self.executor_id:
            raise MirrorRoomError("generator and sandbox evaluator identities must remain independent")
        for field in (
            "spec_digest",
            "manifest_digest",
            "sealed_holdout_digest",
            "split_integrity_digest",
        ):
            object.__setattr__(self, field, _sha256(field, getattr(self, field)))
        if not isinstance(self.production_baseline, MirrorCandidate):
            raise MirrorRoomError("production_baseline must be MirrorCandidate")
        if not isinstance(self.final_sandbox_champion, MirrorCandidate):
            raise MirrorRoomError("final_sandbox_champion must be MirrorCandidate")
        if (
            isinstance(self.validation_candidate_evaluations, bool)
            or not isinstance(self.validation_candidate_evaluations, int)
            or self.validation_candidate_evaluations < 0
        ):
            raise MirrorRoomError("validation_candidate_evaluations must be non-negative")
        if self.production_authority is not False:
            raise MirrorRoomError("Mirror Run cannot have production authority")
        if self.direct_self_modify is not False:
            raise MirrorRoomError("Mirror Run cannot directly self-modify")

        holdout = self.holdout_report
        candidate_changed = (
            self.final_sandbox_champion.candidate_id
            != self.production_baseline.candidate_id
        )
        if holdout is not None:
            if not isinstance(holdout, ComparisonReport):
                raise MirrorRoomError("holdout_report must be ComparisonReport")
            if not candidate_changed:
                raise MirrorRoomError(
                    "holdout report is invalid when final candidate equals production baseline"
                )
            if holdout.run_id != self.run_id:
                raise MirrorRoomError("holdout report run identity mismatch")
            if holdout.split is not ScenarioSplit.HOLDOUT:
                raise MirrorRoomError("holdout report must use sealed holdout split")
            if (
                holdout.baseline_candidate_id
                != self.production_baseline.candidate_id
                or holdout.baseline_candidate_digest
                != self.production_baseline.digest
            ):
                raise MirrorRoomError("holdout report baseline identity mismatch")
            if (
                holdout.candidate_id
                != self.final_sandbox_champion.candidate_id
                or holdout.candidate_digest
                != self.final_sandbox_champion.digest
            ):
                raise MirrorRoomError("holdout report candidate identity mismatch")

        expected = candidate_changed and holdout is not None and holdout.passed
        if self.eligible_for_external_promotion != expected:
            raise MirrorRoomError("promotion eligibility does not match holdout evidence")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "run_id": self.run_id,
                "experiment_id": self.experiment_id,
                "spec_digest": self.spec_digest,
                "manifest_digest": self.manifest_digest,
                "generator_id": self.generator_id,
                "executor_id": self.executor_id,
                "production_baseline_digest": self.production_baseline.digest,
                "final_sandbox_champion_digest": self.final_sandbox_champion.digest,
                "generations": [item.digest for item in self.generations],
                "holdout_report": None if self.holdout_report is None else self.holdout_report.digest,
                "sealed_holdout_digest": self.sealed_holdout_digest,
                "split_integrity_digest": self.split_integrity_digest,
                "validation_candidate_evaluations": self.validation_candidate_evaluations,
                "usage": {
                    "episodes": self.usage.episodes,
                    "steps": self.usage.steps,
                    "tokens": self.usage.tokens,
                    "cost_units": self.usage.cost_units,
                },
                "eligible_for_external_promotion": self.eligible_for_external_promotion,
                "production_authority": False,
                "direct_self_modify": False,
            }
        )


def _merge_hard_examples(
    existing: Sequence[HardExample],
    incoming: Sequence[HardExample],
    *,
    limit: int,
) -> tuple[HardExample, ...]:
    by_id: dict[str, HardExample] = {}
    for item in (*tuple(existing), *tuple(incoming)):
        prior = by_id.get(item.scenario_id)
        if prior is not None and prior.scenario_digest != item.scenario_digest:
            raise MirrorRoomError("hard-example scenario identity drift")
        if prior is None or item.difficulty >= prior.difficulty:
            by_id[item.scenario_id] = item
    ordered = sorted(
        by_id.values(),
        key=lambda item: (-item.difficulty, item.scenario_id),
    )
    return tuple(ordered[:limit])


def _sealed_split_digest(scenarios: Sequence[MirrorScenario]) -> str:
    return _digest(
        {
            "split": ScenarioSplit.HOLDOUT.value,
            "scenario_digests": sorted(item.digest for item in scenarios),
        }
    )


class MirrorRoom:
    """Bounded, isolated, multi-generation learning environment."""

    def __init__(
        self,
        spec: MirrorRoomSpec,
        executor: SandboxExecutor,
    ) -> None:
        if not isinstance(spec, MirrorRoomSpec):
            raise TypeError("spec must be MirrorRoomSpec")
        if not isinstance(executor, SandboxExecutor):
            raise TypeError("executor must satisfy SandboxExecutor")
        generatorless_id = getattr(executor, "executor_id", None)
        if not isinstance(generatorless_id, str) or not generatorless_id.strip():
            raise MirrorRoomError("executor requires a stable identity")
        self.spec = spec
        self.executor = executor

    def _partition(
        self,
        scenarios: Sequence[MirrorScenario],
    ) -> tuple[
        tuple[MirrorScenario, ...],
        tuple[MirrorScenario, ...],
        tuple[MirrorScenario, ...],
    ]:
        items = tuple(scenarios)
        if not items:
            raise MirrorRoomError("Mirror Room requires scenarios")
        if any(not isinstance(item, MirrorScenario) for item in items):
            raise MirrorRoomError("scenarios must contain MirrorScenario")
        validate_split_integrity(items)
        ids = [item.scenario_id for item in items]
        if len(ids) != len(set(ids)):
            raise MirrorRoomError("scenario IDs must be globally unique")
        allowed_data_classes = set(self.spec.manifest.eligibility.allowed_data_classes)
        for item in items:
            if item.data_class not in allowed_data_classes:
                raise MirrorRoomError(
                    "scenario data class exceeds experiment eligibility ceiling"
                )
        payload_owners: dict[str, tuple[str, ScenarioSplit]] = {}
        for item in items:
            if item.payload_digest in payload_owners:
                raise MirrorRoomError(
                    "duplicate scenario payload detected across Mirror Room corpus"
                )
            payload_owners[item.payload_digest] = (item.scenario_id, item.split)
        train = tuple(item for item in items if item.split is ScenarioSplit.TRAIN)
        validation = tuple(item for item in items if item.split is ScenarioSplit.VALIDATION)
        holdout = tuple(item for item in items if item.split is ScenarioSplit.HOLDOUT)
        if not train or not validation or not holdout:
            raise MirrorRoomError("train, validation, and sealed holdout splits are all required")

        min_samples = max(metric.minimum_samples for metric in self.spec.manifest.metrics)
        if len(validation) < min_samples:
            raise MirrorRoomError("validation split does not meet experiment minimum samples")
        if len(holdout) < min_samples:
            raise MirrorRoomError("holdout split does not meet experiment minimum samples")
        return train, validation, holdout

    @staticmethod
    def _generator_identity(generator: CandidateGenerator) -> str:
        if not isinstance(generator, CandidateGenerator):
            raise TypeError("generator must satisfy CandidateGenerator")
        generator_id = getattr(generator, "generator_id", None)
        if not isinstance(generator_id, str) or not generator_id.strip():
            raise MirrorRoomError("candidate generator requires stable generator_id")
        return generator_id

    @staticmethod
    def _validate_candidates(
        candidates: Sequence[MirrorCandidate],
        *,
        generator_id: str,
        champion: MirrorCandidate,
        seen_ids: set[str],
        seen_digests: set[str],
        seen_behavior_digests: set[str],
        limit: int,
    ) -> tuple[MirrorCandidate, ...]:
        result = tuple(candidates)
        if len(result) > limit:
            raise MirrorRoomError("candidate generator exceeded generation limit")
        local_ids: set[str] = set()
        local_digests: set[str] = set()
        local_behavior_digests: set[str] = set()
        for candidate in result:
            if not isinstance(candidate, MirrorCandidate):
                raise MirrorRoomError("candidate generator returned invalid object")
            if candidate.producer_id != generator_id:
                raise MirrorRoomError("candidate producer identity does not match generator")
            if candidate.parent_candidate_id != champion.candidate_id:
                raise MirrorRoomError("candidate lineage is not rooted in current sandbox champion")
            if candidate.candidate_id == champion.candidate_id:
                raise MirrorRoomError("candidate identity aliases current champion")
            if candidate.candidate_id in seen_ids or candidate.candidate_id in local_ids:
                raise MirrorRoomError("candidate identity was reused in one learning run")
            if (
                candidate.digest in seen_digests
                or candidate.digest in local_digests
            ):
                raise MirrorRoomError("duplicate candidate content was proposed")
            if (
                candidate.behavior_digest in seen_behavior_digests
                or candidate.behavior_digest in local_behavior_digests
            ):
                raise MirrorRoomError(
                    "candidate behavior was already explored in this learning run"
                )
            local_ids.add(candidate.candidate_id)
            local_digests.add(candidate.digest)
            local_behavior_digests.add(candidate.behavior_digest)
        return result

    def learn(
        self,
        *,
        run_id: str,
        generator: CandidateGenerator,
        scenarios: Sequence[MirrorScenario],
        generations: int | None = None,
    ) -> MirrorRunReceipt:
        if not isinstance(run_id, str) or not run_id.strip():
            raise MirrorRoomError("run_id must be non-empty")
        generator_id = self._generator_identity(generator)
        executor_id = self.executor.executor_id
        if generator_id == executor_id:
            raise MirrorRoomError(
                "candidate generator and sandbox evaluator must be independent"
            )
        split_integrity = validate_split_integrity(scenarios)
        train, validation, holdout = self._partition(scenarios)
        generation_limit = (
            self.spec.budget.max_generations if generations is None else generations
        )
        if (
            isinstance(generation_limit, bool)
            or not isinstance(generation_limit, int)
            or generation_limit <= 0
            or generation_limit > self.spec.budget.max_generations
        ):
            raise MirrorRoomError("requested generations exceed Mirror Room budget")

        sandbox = MirrorSandbox(self.spec, self.executor)
        evaluator = PairedEvaluator(self.spec, sandbox)
        production_baseline = self.spec.production_baseline

        # Keep the adaptive learner and qualification tracks separate. The
        # generator sees only the TRAIN-selected learning champion; validation
        # can qualify a production candidate but cannot choose the next parent.
        learning_champion = production_baseline
        qualified_champion = production_baseline
        qualified_score = float("-inf")
        seen_ids = {production_baseline.candidate_id}
        seen_digests = {production_baseline.digest}
        seen_behavior_digests = {production_baseline.behavior_digest}
        hard_examples: tuple[HardExample, ...] = ()
        prior_candidate_id: str | None = None
        generation_records: list[GenerationRecord] = []
        stagnant_generations = 0
        validation_candidate_evaluations = 0
        validation_family_size = (
            generation_limit * self.spec.budget.max_candidates_per_generation
        )

        for generation in range(1, generation_limit + 1):
            curriculum = build_curriculum(train, hard_examples)
            feedback = LearningFeedback(
                generation=generation,
                champion=learning_champion,
                training_scenarios=curriculum.scenarios,
                hard_examples=hard_examples,
                prior_candidate_id=prior_candidate_id,
            )
            proposed = generator.propose(
                feedback,
                limit=self.spec.budget.max_candidates_per_generation,
            )
            candidates = self._validate_candidates(
                proposed,
                generator_id=generator_id,
                champion=learning_champion,
                seen_ids=seen_ids,
                seen_digests=seen_digests,
                seen_behavior_digests=seen_behavior_digests,
                limit=self.spec.budget.max_candidates_per_generation,
            )
            if not candidates:
                break

            incoming_learning = learning_champion
            raw: list[
                tuple[MirrorCandidate, ComparisonReport, ComparisonReport]
            ] = []
            for candidate in candidates:
                training_report = evaluator.compare(
                    run_id=run_id,
                    baseline=incoming_learning,
                    candidate=candidate,
                    scenarios=train,
                    split=ScenarioSplit.TRAIN,
                    enforce_gate=False,
                )
                validation_candidate_evaluations += 1
                if (
                    validation_candidate_evaluations
                    > self.spec.budget.max_validation_candidate_evaluations
                ):
                    raise MirrorRoomError(
                        "Mirror Room validation selection budget exhausted"
                    )
                validation_report = evaluator.compare(
                    run_id=run_id,
                    baseline=production_baseline,
                    candidate=candidate,
                    scenarios=validation,
                    split=ScenarioSplit.VALIDATION,
                    enforce_gate=True,
                    comparison_family_size=validation_family_size,
                )
                raw.append(
                    (candidate, training_report, validation_report)
                )
                seen_ids.add(candidate.candidate_id)
                seen_digests.add(candidate.digest)
                seen_behavior_digests.add(candidate.behavior_digest)

            ranked_training = sorted(
                raw,
                key=lambda item: (
                    -item[1].weighted_utility_delta,
                    item[0].candidate_id,
                ),
            )
            learning_selected: MirrorCandidate | None = None
            learning_report: ComparisonReport | None = None
            if (
                ranked_training
                and ranked_training[0][1].weighted_utility_delta > 0.0
            ):
                learning_selected, learning_report, _ = ranked_training[0]
                learning_champion = learning_selected
                stagnant_generations = 0
            else:
                stagnant_generations += 1

            passing = [item for item in raw if item[2].passed]
            qualification_selected: MirrorCandidate | None = None
            if passing:
                best_qualified = sorted(
                    passing,
                    key=lambda item: (
                        -item[2].weighted_utility_delta,
                        -item[1].weighted_utility_delta,
                        item[0].candidate_id,
                    ),
                )[0]
                if (
                    best_qualified[2].weighted_utility_delta
                    > qualified_score
                ):
                    qualification_selected = best_qualified[0]
                    qualified_champion = best_qualified[0]
                    qualified_score = (
                        best_qualified[2].weighted_utility_delta
                    )

            # All adaptive feedback remains TRAIN-derived.
            feedback_source = learning_report
            if feedback_source is None and ranked_training:
                feedback_source = ranked_training[0][1]
            newest_hard_examples = (
                ()
                if feedback_source is None
                else feedback_source.hard_examples(
                    limit=self.spec.hard_example_limit
                )
            )
            hard_examples = _merge_hard_examples(
                hard_examples,
                newest_hard_examples,
                limit=self.spec.hard_example_limit,
            )
            prior_candidate_id = (
                learning_selected.candidate_id
                if learning_selected is not None
                else (
                    ranked_training[0][0].candidate_id
                    if ranked_training
                    else None
                )
            )

            evaluations = tuple(
                CandidateEvaluation(
                    candidate=candidate,
                    training_report=training_report,
                    validation_report=validation_report,
                    selected_for_learning=(
                        learning_selected is not None
                        and candidate.candidate_id
                        == learning_selected.candidate_id
                    ),
                    selected=(
                        qualification_selected is not None
                        and candidate.candidate_id
                        == qualification_selected.candidate_id
                    ),
                )
                for candidate, training_report, validation_report in raw
            )
            generation_records.append(
                GenerationRecord(
                    generation=generation,
                    incoming_champion_id=incoming_learning.candidate_id,
                    evaluations=evaluations,
                    learning_champion_id=learning_champion.candidate_id,
                    selected_champion_id=qualified_champion.candidate_id,
                    hard_examples=hard_examples,
                    curriculum_digest=curriculum.digest,
                )
            )
            if stagnant_generations >= self.spec.stagnation_patience:
                break

        holdout_report: ComparisonReport | None = None
        if (
            qualified_champion.candidate_id
            != production_baseline.candidate_id
        ):
            holdout_report = evaluator.compare(
                run_id=run_id,
                baseline=production_baseline,
                candidate=qualified_champion,
                scenarios=holdout,
                split=ScenarioSplit.HOLDOUT,
                enforce_gate=True,
            )

        eligible = (
            qualified_champion.candidate_id
            != production_baseline.candidate_id
            and holdout_report is not None
            and holdout_report.passed
        )
        return MirrorRunReceipt(
            run_id=run_id,
            experiment_id=self.spec.manifest.experiment_id,
            spec_digest=self.spec.digest,
            manifest_digest=self.spec.manifest.manifest_digest,
            generator_id=generator_id,
            executor_id=executor_id,
            production_baseline=production_baseline,
            final_sandbox_champion=qualified_champion,
            generations=tuple(generation_records),
            holdout_report=holdout_report,
            sealed_holdout_digest=_sealed_split_digest(holdout),
            split_integrity_digest=split_integrity.digest,
            validation_candidate_evaluations=validation_candidate_evaluations,
            usage=sandbox.usage,
            eligible_for_external_promotion=eligible,
        )


__all__ = [
    "CandidateEvaluation",
    "CandidateGenerator",
    "GenerationRecord",
    "MirrorRoom",
    "MirrorRunReceipt",
]

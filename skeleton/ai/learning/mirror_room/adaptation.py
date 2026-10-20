"""Bounded local neural ranking and numeric adaptation for Mirror Room.

The two-hidden-layer reward/cost predictor learns from completed paired TRAIN
episodes and retains clipped Adam state in the existing learning archive.
It proposes only explicit bounded numeric edits. Validation, sealed holdout,
quality thresholds and production authority remain independent.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from types import MappingProxyType
from typing import Mapping, Sequence

from .contracts import (
    LearningFeedback,
    MirrorCandidate,
    MirrorRoomError,
    MirrorRoomSpec,
    MirrorScenario,
    ScenarioSplit,
    _digest,
    _finite,
    _sha256,
    _text,
    _token,
)
from .memory import LearnerCheckpoint, TrainingLearningArchive, TrainingObservation


@dataclass(frozen=True, slots=True)
class AdaptiveLearningPolicy:
    """Fixed computational limits for local candidate-ranking adaptation."""

    learning_rate: float = 0.002
    gradient_clip: float = 1.0
    weight_decay: float = 0.0001
    updates_per_observation: int = 4
    replay_batch_size: int = 16
    minimum_rank_observations: int = 4
    uncertainty_bonus: float = 0.25
    diversity_bonus: float = 0.15
    cost_penalty: float = 0.1
    reward_scale: float = 1.0
    max_candidate_pool: int = 256

    def __post_init__(self) -> None:
        for name in ("learning_rate", "gradient_clip", "weight_decay", "uncertainty_bonus", "diversity_bonus", "cost_penalty", "reward_scale"):
            value = _finite(name, getattr(self, name), minimum=0.0)
            if value > 100.0 or (name in {"learning_rate", "gradient_clip", "reward_scale"} and value <= 0.0):
                raise MirrorRoomError("adaptive learning scalar exceeds bounded policy")
            object.__setattr__(self, name, value)
        for name, maximum in (("updates_per_observation", 16), ("replay_batch_size", 64), ("minimum_rank_observations", 2048), ("max_candidate_pool", 512)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                raise MirrorRoomError(f"{name} exceeds bounded learning policy")

    @property
    def digest(self) -> str:
        return _digest({name: getattr(self, name) for name in self.__dataclass_fields__})


class _BoundedNeuralPredictor:
    """Two hidden tanh layers, reward/cost heads, clipped Adam and replay.

    Pure numeric local inference avoids introducing a provider or optional ML
    service. Only the small ranking model changes; game/model artifacts and
    promotion authority remain outside this optimizer.
    """

    def __init__(self, feature_count: int, seed_digest: str, policy: AdaptiveLearningPolicy) -> None:
        self.architecture = (feature_count, 16, 8, 2)
        self.policy = policy
        rng = random.Random(int(seed_digest, 16))
        self.weights: list[float] = []
        self.offsets: list[int] = []
        for left, right in zip(self.architecture, self.architecture[1:]):
            self.offsets.append(len(self.weights))
            bound = math.sqrt(6.0 / (left + right))
            for _ in range(right):
                self.weights.extend(rng.uniform(-bound, bound) for _ in range(left))
                self.weights.append(0.0)
        self.first = [0.0] * len(self.weights)
        self.second = [0.0] * len(self.weights)
        self.training_steps = 0
        self.observations_seen = 0
        self.rejected_updates = 0
        self.residual_variance = 1.0

    def forward(self, features: Sequence[float], *, weights: Sequence[float] | None = None) -> list[list[float]]:
        if len(features) != self.architecture[0] or any(not math.isfinite(value) for value in features):
            raise MirrorRoomError("neural predictor feature shape or finiteness mismatch")
        activations = [list(features)]
        actual_weights = self.weights if weights is None else weights
        for layer, (left, right) in enumerate(zip(self.architecture, self.architecture[1:])):
            incoming = activations[-1]
            offset = self.offsets[layer]
            outgoing = []
            for unit in range(right):
                start = offset + unit * (left + 1)
                value = actual_weights[start + left] + sum(actual_weights[start + index] * incoming[index] for index in range(left))
                outgoing.append(math.tanh(value))
            activations.append(outgoing)
        return activations

    def predict(self, features: Sequence[float]) -> tuple[float, float]:
        output = self.forward(features)[-1]
        return output[0], output[1]

    def targets(self, observation: TrainingObservation) -> tuple[float, float]:
        reward = math.tanh(observation.training_utility_delta / self.policy.reward_scale)
        if not observation.guardrails_passed:
            reward = min(reward, -0.5)
        return reward, math.tanh(math.log1p(observation.cost_units) / 10.0)

    def _replay_loss(self, observations: Sequence[TrainingObservation], weights: Sequence[float]) -> float:
        total = 0.0
        for observation in observations:
            for prediction, target in zip(self.forward(observation.features, weights=weights)[-1], self.targets(observation), strict=True):
                error = abs(prediction - target)
                total += 0.5 * error * error if error <= 1.0 else error - 0.5
        return total / len(observations)

    def train_batch(self, observations: Sequence[TrainingObservation]) -> bool:
        if not observations or len(observations) > self.policy.replay_batch_size:
            raise MirrorRoomError("neural replay batch exceeds declared bounds")
        gradients = [0.0] * len(self.weights)
        for observation in observations:
            activations = self.forward(observation.features)
            targets = self.targets(observation)
            # Huber derivative bounds influence from unusually large errors.
            deltas = [max(-1.0, min(1.0, value - target)) * (1.0 - value * value) for value, target in zip(activations[-1], targets)]
            for layer in range(2, -1, -1):
                left, right = self.architecture[layer:layer + 2]
                offset = self.offsets[layer]
                incoming = activations[layer]
                previous = [0.0] * left
                for unit in range(right):
                    start = offset + unit * (left + 1)
                    for index in range(left):
                        gradients[start + index] += deltas[unit] * incoming[index] / len(observations)
                        previous[index] += self.weights[start + index] * deltas[unit]
                    gradients[start + left] += deltas[unit] / len(observations)
                if layer:
                    deltas = [value * (1.0 - incoming[index] ** 2) for index, value in enumerate(previous)]
        norm = math.sqrt(sum(value * value for value in gradients))
        if not math.isfinite(norm):
            self.rejected_updates += 1
            return False
        scale = min(1.0, self.policy.gradient_clip / max(norm, 1e-12))
        step = self.training_steps + 1
        proposed_weights, proposed_first, proposed_second = [], [], []
        for weight, first, second, gradient in zip(self.weights, self.first, self.second, gradients, strict=True):
            clipped = gradient * scale
            moment = 0.9 * first + 0.1 * clipped
            variance = 0.999 * second + 0.001 * clipped * clipped
            update = self.policy.learning_rate * ((moment / (1.0 - 0.9 ** step)) / (math.sqrt(variance / (1.0 - 0.999 ** step)) + 1e-8) + self.policy.weight_decay * weight)
            value = weight - update
            if not all(math.isfinite(item) and abs(item) <= 1e6 for item in (value, moment, variance)):
                self.rejected_updates += 1
                return False
            proposed_weights.append(value)
            proposed_first.append(moment)
            proposed_second.append(variance)
        previous_loss = self._replay_loss(observations, self.weights)
        proposed_loss = self._replay_loss(observations, proposed_weights)
        if not math.isfinite(proposed_loss) or proposed_loss > previous_loss + max(1e-5, previous_loss * 0.05):
            self.rejected_updates += 1
            return False
        # Keep the prior numeric ranker when an optimizer step destabilizes its
        # observed replay loss. This is a TRAIN optimization barrier; independent
        # game-quality and release gates still authorize candidate acceptance.
        self.weights, self.first, self.second = proposed_weights, proposed_first, proposed_second
        self.training_steps = step
        return True

    def restore(self, checkpoint: LearnerCheckpoint) -> None:
        if checkpoint.architecture != self.architecture:
            raise MirrorRoomError("learner checkpoint architecture mismatch")
        self.weights = list(checkpoint.weights)
        self.first = list(checkpoint.optimizer_first)
        self.second = list(checkpoint.optimizer_second)
        self.training_steps = checkpoint.training_steps
        self.observations_seen = checkpoint.observations_seen
        self.rejected_updates = checkpoint.rejected_updates
        self.residual_variance = checkpoint.residual_variance


@dataclass(frozen=True, slots=True)
class NumericDimension:
    """One bounded numeric coordinate the reference learner may adapt."""

    name: str
    lower: float
    upper: float
    initial_step: float
    min_step: float = 1e-4
    expansion: float = 1.5
    contraction: float = 0.5

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _token("dimension name", self.name))
        lower = _finite("dimension lower", self.lower)
        upper = _finite("dimension upper", self.upper)
        if upper <= lower or not math.isfinite(upper - lower):
            raise MirrorRoomError("numeric dimension requires a finite positive span")
        step = _finite("initial_step", self.initial_step, minimum=0.0)
        minimum = _finite("min_step", self.min_step, minimum=0.0)
        expansion = _finite("expansion", self.expansion, minimum=0.0)
        contraction = _finite(
            "contraction",
            self.contraction,
            minimum=0.0,
        )
        if step <= 0.0 or minimum <= 0.0:
            raise MirrorRoomError("numeric dimension steps must be positive")
        if step < minimum:
            raise MirrorRoomError("initial_step cannot be smaller than min_step")
        if step > upper - lower:
            raise MirrorRoomError("initial_step cannot exceed dimension span")
        if expansion <= 1.0:
            raise MirrorRoomError("expansion must be greater than one")
        if not 0.0 < contraction < 1.0:
            raise MirrorRoomError("contraction must be within (0, 1)")
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)
        object.__setattr__(self, "initial_step", step)
        object.__setattr__(self, "min_step", minimum)
        object.__setattr__(self, "expansion", expansion)
        object.__setattr__(self, "contraction", contraction)

    @property
    def max_step(self) -> float:
        return self.upper - self.lower

    @property
    def digest(self) -> str:
        return _digest(
            {
                "name": self.name,
                "lower": self.lower,
                "upper": self.upper,
                "initial_step": self.initial_step,
                "min_step": self.min_step,
                "expansion": self.expansion,
                "contraction": self.contraction,
            }
        )


class DeterministicCoordinateLearner:
    """Resumable neural-guided derivative-free search over numeric parameters.

    Deterministic coordinates bootstrap the first TRAIN observations. A bounded
    local predictor then ranks single and interacting edits using observed
    reward, measured cost, uncertainty and batch diversity. Existing callers
    retain this class and constructor; completed-outcome hooks are optional on
    other CandidateGenerator implementations.
    """

    def __init__(
        self,
        *,
        generator_id: str,
        dimensions: Sequence[NumericDimension],
        training_archive: TrainingLearningArchive | None = None,
        learning_policy: AdaptiveLearningPolicy | None = None,
    ) -> None:
        self.generator_id = _token("generator_id", generator_id)
        rows = tuple(dimensions)
        if not rows or len(rows) > 64:
            raise MirrorRoomError("coordinate learner requires 1..64 dimensions")
        if any(not isinstance(item, NumericDimension) for item in rows):
            raise MirrorRoomError(
                "dimensions must contain NumericDimension values"
            )
        names = [item.name for item in rows]
        if len(names) != len(set(names)):
            raise MirrorRoomError("numeric dimension names must be unique")
        self.dimensions = tuple(sorted(rows, key=lambda item: item.name))
        if (
            training_archive is not None
            and not isinstance(
                training_archive,
                TrainingLearningArchive,
            )
        ):
            raise MirrorRoomError(
                "training_archive must be TrainingLearningArchive"
            )
        self.training_archive = (
            training_archive
            if training_archive is not None
            else TrainingLearningArchive()
        )
        self._initial_archive_digest = self.training_archive.digest
        self._checkpoint_digest: str | None = None
        self._steps = {
            item.name: min(
                item.max_step,
                max(
                    item.min_step,
                    self.training_archive.suggested_step(
                        item.name,
                        item.initial_step,
                    ),
                ),
            )
            for item in self.dimensions
        }
        self._last_parent_parameters: dict[str, float] | None = None
        if learning_policy is not None and not isinstance(learning_policy, AdaptiveLearningPolicy):
            raise MirrorRoomError("learning_policy must be AdaptiveLearningPolicy")
        self.learning_policy = learning_policy or AdaptiveLearningPolicy()
        self._context_digest: str | None = None
        self._feature_schema_digest = _digest({
            "schema_version": 1,
            "dimensions": [item.digest for item in self.dimensions],
            "features": "per-dimension-parent-target-delta-absolute/v1-plus-edit-summary",
            "learning_policy": self.learning_policy.digest,
        })
        self._predictor: _BoundedNeuralPredictor | None = None
        self._bound_spec: MirrorRoomSpec | None = None
        self._bound_experiment_id: str | None = None
        self._numeric_workload_digest: str | None = None
        self._bound_executor_id: str | None = None
        self._bound_train: dict[str, MirrorScenario] = {}
        self._proposed_parameters: set[str] = set()
        self._pending_candidates: dict[str, str] = {}

    @property
    def strategy_digest(self) -> str:
        return _digest(
            {
                "generator_id": self.generator_id,
                "dimensions": [item.digest for item in self.dimensions],
                "training_archive_digest": self._initial_archive_digest,
                "training_checkpoint_digest": self._checkpoint_digest,
                "feature_schema_digest": self._feature_schema_digest,
                "context_digest": self._context_digest,
            }
        )

    def bind_training(self, *, spec: MirrorRoomSpec, executor_id: str, scenarios: Sequence[MirrorScenario]) -> None:
        """Bind immutable TRAIN context before any model receives outcomes."""

        if not isinstance(spec, MirrorRoomSpec):
            raise MirrorRoomError("learner context requires MirrorRoomSpec")
        executor = _text("executor_id", executor_id)
        train = tuple(scenarios)
        if not train or any(not isinstance(item, MirrorScenario) or item.split is not ScenarioSplit.TRAIN for item in train):
            raise MirrorRoomError("learner context accepts only TRAIN scenarios")
        if len({item.digest for item in train}) != len(train):
            raise MirrorRoomError("learner context contains duplicate TRAIN scenarios")
        context = _digest({
            "schema_version": 1,
            "spec_digest": spec.digest,
            "executor_id": executor,
            "generator_id": self.generator_id,
            "training_scenarios": sorted(item.digest for item in train),
            "feature_schema_digest": self._feature_schema_digest,
        })
        self._context_digest = context
        self._checkpoint_digest = None
        self._bound_spec = spec
        self._bound_experiment_id = spec.manifest.experiment_id
        self._numeric_workload_digest = None
        self._bound_executor_id = executor
        self._bound_train = {item.digest: item for item in train}
        self._last_parent_parameters = None
        self._proposed_parameters = {_digest(dict(spec.production_baseline.parameters))}
        self._pending_candidates.clear()
        self._predictor = _BoundedNeuralPredictor(4 * len(self.dimensions) + 3, context, self.learning_policy)
        checkpoint = self.training_archive.checkpoint_for(context, self._feature_schema_digest, self.generator_id)
        # Never warm-start numeric edits or rewards from a different corpus,
        # metric policy, executor, baseline or feature normalization.
        self._steps = {item.name: item.initial_step for item in self.dimensions}
        if checkpoint is not None:
            self._checkpoint_digest = checkpoint.digest
            if checkpoint.experiment_id != spec.manifest.experiment_id or set(checkpoint.step_sizes) != {item.name for item in self.dimensions}:
                raise MirrorRoomError("learner checkpoint experiment or dimension context mismatch")
            self._predictor.restore(checkpoint)
            for dimension in self.dimensions:
                value = checkpoint.step_sizes[dimension.name]
                if not dimension.min_step <= value <= dimension.max_step:
                    raise MirrorRoomError("restored learner step exceeds hard dimension bounds")
                self._steps[dimension.name] = value
        replay = self.training_archive.for_context(context, self._feature_schema_digest)
        for observation in replay:
            if observation.experiment_id != spec.manifest.experiment_id or set(observation.scenario_digests) != set(self._bound_train) or len(observation.features) != self._predictor.architecture[0]:
                raise MirrorRoomError("restored TRAIN observation does not match its bound context")
        if checkpoint is not None and (checkpoint.observations_seen < len(replay) or checkpoint.training_steps + checkpoint.rejected_updates != checkpoint.observations_seen * self.learning_policy.updates_per_observation):
            raise MirrorRoomError("restored optimizer counters do not match completed TRAIN updates")
        if checkpoint is None and replay:
            # Rebuild only when numeric observations survive but no optimizer
            # checkpoint does; deterministic order preserves reproducibility.
            for observation in replay:
                self._learn_observation(observation, replay=(observation,))

    def bind_numeric_observations(self, *, context_digest: str, experiment_id: str, workload_digest: str) -> None:
        """Bind an application-owned, explicitly admitted numeric workload.

        Application callers verify their own immutable review/job receipts and
        consent before admission. This path does not manufacture sandbox,
        validation, holdout, or promotion receipts for ordinary studio reviews.
        """

        owner_context = _sha256("owner numeric context", context_digest)
        workload = _sha256("numeric workload", workload_digest)
        experiment = _token("numeric experiment", experiment_id)
        context = _digest({"schema_version": 1, "owner_numeric_context": owner_context, "workload_digest": workload, "experiment_id": experiment, "generator_id": self.generator_id, "feature_schema_digest": self._feature_schema_digest})
        self._context_digest = context
        self._bound_experiment_id = experiment
        self._numeric_workload_digest = workload
        self._bound_spec = None
        self._bound_executor_id = None
        self._bound_train = {}
        self._pending_candidates.clear()
        self._proposed_parameters.clear()
        self._last_parent_parameters = None
        self._checkpoint_digest = None
        self._predictor = _BoundedNeuralPredictor(4 * len(self.dimensions) + 3, context, self.learning_policy)
        self._steps = {item.name: item.initial_step for item in self.dimensions}
        checkpoint = self.training_archive.checkpoint_for(context, self._feature_schema_digest, self.generator_id)
        replay = self.training_archive.for_context(context, self._feature_schema_digest)
        for observation in replay:
            if observation.experiment_id != experiment or observation.scenario_digests != (workload,) or len(observation.features) != self._predictor.architecture[0]:
                raise MirrorRoomError("numeric replay differs from the admitted owner workload")
        if checkpoint is not None:
            if checkpoint.experiment_id != experiment or checkpoint.observations_seen < len(replay) or checkpoint.training_steps + checkpoint.rejected_updates != checkpoint.observations_seen * self.learning_policy.updates_per_observation:
                raise MirrorRoomError("numeric checkpoint lineage or optimizer counter mismatch")
            if set(checkpoint.step_sizes) != {item.name for item in self.dimensions}:
                raise MirrorRoomError("numeric checkpoint dimensions mismatch")
            self._predictor.restore(checkpoint)
            for dimension in self.dimensions:
                step = checkpoint.step_sizes[dimension.name]
                if not dimension.min_step <= step <= dimension.max_step:
                    raise MirrorRoomError("numeric checkpoint step exceeds explicit bounds")
                self._steps[dimension.name] = step
            self._checkpoint_digest = checkpoint.digest
        else:
            for observation in replay:
                self._learn_observation(observation, replay=(observation,))

    def observe_numeric_training(self, *, run_id: str, generation: int, candidate_id: str, parent_parameters: Mapping[str, object], candidate_parameters: Mapping[str, object], parent_behavior_digest: str, candidate_behavior_digest: str, report_digest: str, utility_delta: float, cost_units: float, guardrails_passed: bool) -> None:
        """Admit verified numeric facts from the bound application owner only.

        The owner supplies measured reward/cost and stable protocol identity.
        A caller cannot use this method to inject observations into a sandbox
        experiment that requires paired EpisodeReceipts.
        """

        if self._bound_spec is not None or self._numeric_workload_digest is None or self._context_digest is None or self._bound_experiment_id is None:
            raise MirrorRoomError("numeric observations require their distinct owner-bound context")
        observation = TrainingObservation(
            context_digest=self._context_digest, feature_schema_digest=self._feature_schema_digest,
            experiment_id=self._bound_experiment_id, run_id=run_id, generation=generation,
            parent_behavior_digest=parent_behavior_digest, candidate_behavior_digest=candidate_behavior_digest,
            candidate_id=candidate_id, training_report_digest=report_digest,
            scenario_digests=(self._numeric_workload_digest,), features=self._features(parent_parameters, candidate_parameters),
            training_utility_delta=utility_delta, cost_units=cost_units, guardrails_passed=guardrails_passed,
            scenario_utilities={self._numeric_workload_digest: utility_delta},
        )
        self._remember_observation(observation)

    def rank_numeric_edits(self, *, parameters: Mapping[str, object], generation: int, limit: int = 3) -> tuple[Mapping[str, object], ...]:
        """Return quarantined numeric edit advice without dispatch authority."""

        if self._numeric_workload_digest is None or self._context_digest is None:
            raise MirrorRoomError("numeric advice requires an admitted owner workload")
        parent_digest = _digest(dict(parameters))
        self._proposed_parameters.add(parent_digest)
        parent = MirrorCandidate(candidate_id=f"numeric-parent-{parent_digest[:24]}", version="numeric-ranking-v1", producer_id=self.generator_id, change_ref="numeric-advice-parent", change_digest=parent_digest, parameters=parameters)
        feedback = LearningFeedback(generation=generation, champion=parent, training_scenarios=(), hard_examples=())
        # These are ordinary proposed parameters, never execution receipts.
        proposed = self.propose(feedback, limit=limit)
        return tuple(MappingProxyType(dict(item.parameters)) for item in proposed)

    @property
    def learning_status(self) -> Mapping[str, object]:
        model = self._predictor
        return MappingProxyType({
            "context_digest": self._context_digest,
            "feature_schema_digest": self._feature_schema_digest,
            "checkpoint_digest": self._checkpoint_digest,
            "training_steps": 0 if model is None else model.training_steps,
            "observations_seen": 0 if model is None else model.observations_seen,
            "rejected_updates": 0 if model is None else model.rejected_updates,
            "replay_size": 0 if self._context_digest is None else len(self.training_archive.for_context(self._context_digest, self._feature_schema_digest)),
            "production_authority": False,
        })

    def _features(self, parent: Mapping[str, object], candidate: Mapping[str, object]) -> tuple[float, ...]:
        features: list[float] = []
        absolute_deltas = []
        for dimension in self.dimensions:
            before = _finite(f"parent {dimension.name}", parent.get(dimension.name))
            after = _finite(f"candidate {dimension.name}", candidate.get(dimension.name))
            if not dimension.lower <= before <= dimension.upper or not dimension.lower <= after <= dimension.upper:
                raise MirrorRoomError("learner features exceed explicit parameter bounds")
            span = dimension.max_step
            delta = (after - before) / span
            features.extend(((before - dimension.lower) / span, (after - dimension.lower) / span, delta, abs(delta)))
            absolute_deltas.append(abs(delta))
        features.extend((sum(absolute_deltas) / len(absolute_deltas), max(absolute_deltas), sum(value > 1e-15 for value in absolute_deltas) / len(absolute_deltas)))
        return tuple(features)

    def observe_training(self, *, generation: int, parent: MirrorCandidate, candidate: MirrorCandidate, report: object) -> None:
        """Learn once from completed paired TRAIN receipts, never verdicts.

        Adversarial reports may contain a growing challenge corpus. Their
        fixed, initially bound TRAIN subset supplies the comparable reward;
        validation acceptance and challenge-only reward cannot contaminate it.
        """

        from .evaluation import ComparisonReport

        spec = self._bound_spec
        context = self._context_digest
        if spec is None or context is None or self._predictor is None:
            raise MirrorRoomError("learner must bind its TRAIN context before observations")
        if not isinstance(report, ComparisonReport) or report.split is not ScenarioSplit.TRAIN:
            raise MirrorRoomError("online learner accepts completed TRAIN comparison reports only")
        if not isinstance(parent, MirrorCandidate) or not isinstance(candidate, MirrorCandidate):
            raise MirrorRoomError("training observation requires exact candidate lineage")
        if candidate.producer_id != self.generator_id or candidate.parent_candidate_id != parent.candidate_id:
            raise MirrorRoomError("training observation candidate producer or parent mismatch")
        previous_observation = next((item for item in self.training_archive.observations if item.training_report_digest == report.digest), None)
        if previous_observation is None and self._pending_candidates.get(candidate.digest) != parent.digest:
            raise MirrorRoomError("training outcome does not belong to an issued pending numeric proposal")
        editable = {item.name for item in self.dimensions}
        if set(parent.parameters) != set(candidate.parameters) or any(parent.parameters[name] != candidate.parameters[name] for name in set(parent.parameters) - editable):
            raise MirrorRoomError("numeric learner cannot attribute unrelated artifact parameter changes")
        if (report.baseline_candidate_id, report.baseline_candidate_digest, report.candidate_id, report.candidate_digest) != (parent.candidate_id, parent.digest, candidate.candidate_id, candidate.digest):
            raise MirrorRoomError("training observation report lineage mismatch")
        rows = {}
        for row in report.scenario_comparisons:
            if row.scenario_digest in rows:
                raise MirrorRoomError("training report repeats a scenario")
            for receipt, expected in ((row.baseline_receipt, parent), (row.candidate_receipt, candidate)):
                if (receipt.run_id != report.run_id or receipt.split != ScenarioSplit.TRAIN.value
                    or receipt.executor_id != self._bound_executor_id or receipt.spec_digest != spec.digest
                    or receipt.candidate_id != expected.candidate_id or receipt.candidate_digest != expected.digest
                    or receipt.scenario_digest != row.scenario_digest or receipt.scenario_id != row.scenario_id):
                    raise MirrorRoomError("training episode receipt context mismatch")
            if row.baseline_receipt.seed != row.candidate_receipt.seed:
                raise MirrorRoomError("training episode receipts are not paired")
            rows[row.scenario_digest] = row
        if not set(self._bound_train).issubset(rows):
            raise MirrorRoomError("training report does not cover the bound fixed TRAIN corpus")
        selected = [rows[key] for key in sorted(self._bound_train)]
        total_weight = sum(item.weight for item in self._bound_train.values())
        utility = 0.0
        scenario_utilities = {}
        guardrails_passed = True
        cost = 0.0
        for row in selected:
            scenario = self._bound_train[row.scenario_digest]
            if row.scenario_id != scenario.scenario_id or row.weight != scenario.weight:
                raise MirrorRoomError("training report scenario identity or weight drift")
            weighted = 0.0
            metric_weight = 0.0
            if set(row.metric_deltas) != {item.metric_id for item in spec.metrics}:
                raise MirrorRoomError("training report metric context mismatch")
            for metric in spec.metrics:
                before = _finite("baseline metric", row.baseline_receipt.outcome.metric_values[metric.metric_id])
                after = _finite("candidate metric", row.candidate_receipt.outcome.metric_values[metric.metric_id])
                delta = after - before if metric.direction.value == "maximize" else before - after
                if not math.isclose(delta, _finite("TRAIN metric delta", row.metric_deltas[metric.metric_id]), rel_tol=1e-10, abs_tol=1e-12):
                    raise MirrorRoomError("TRAIN reward differs from paired episode evidence")
                weighted += delta * metric.weight
                metric_weight += metric.weight
                if metric.guardrail and delta < -metric.max_regression:
                    guardrails_passed = False
            scenario_utility = weighted / metric_weight
            if not math.isclose(scenario_utility, _finite("TRAIN scenario utility", row.utility_delta), rel_tol=1e-10, abs_tol=1e-12):
                raise MirrorRoomError("TRAIN scenario utility differs from paired evidence")
            scenario_utilities[row.scenario_digest] = scenario_utility
            utility += scenario_utility * scenario.weight / total_weight
            cost += _finite("observed candidate cost", row.candidate_receipt.outcome.cost_units, minimum=0.0)
        observation = TrainingObservation(
            context_digest=context, feature_schema_digest=self._feature_schema_digest,
            experiment_id=spec.manifest.experiment_id, run_id=report.run_id, generation=generation,
            parent_behavior_digest=parent.behavior_digest, candidate_behavior_digest=candidate.behavior_digest,
            candidate_id=candidate.candidate_id, training_report_digest=report.digest,
            scenario_digests=tuple(self._bound_train), features=self._features(parent.parameters, candidate.parameters),
            training_utility_delta=utility, cost_units=cost, guardrails_passed=guardrails_passed,
            scenario_utilities=scenario_utilities,
        )
        self._remember_observation(observation)
        self._pending_candidates.pop(candidate.digest, None)

    def _remember_observation(self, observation: TrainingObservation) -> None:
        if observation.context_digest != self._context_digest or observation.feature_schema_digest != self._feature_schema_digest:
            raise MirrorRoomError("numeric observation context or feature schema differs")
        updated = self.training_archive.with_observation(observation)
        if updated is self.training_archive:
            return
        self.training_archive = updated
        replay = self.training_archive.for_context(observation.context_digest, self._feature_schema_digest)
        self._learn_observation(observation, replay=replay)
        for index, dimension in enumerate(self.dimensions):
            if abs(observation.features[4 * index + 2]) <= 1e-15:
                continue
            factor = dimension.expansion if observation.training_utility_delta > 0.0 and observation.guardrails_passed else dimension.contraction
            self._steps[dimension.name] = min(dimension.max_step, max(dimension.min_step, self._steps[dimension.name] * factor))
        self._save_checkpoint()

    def curriculum_priorities(self) -> Mapping[str, float]:
        """Bounded difficulty/progress scores from the fixed TRAIN corpus."""

        if self._context_digest is None:
            return MappingProxyType({})
        replay = self.training_archive.for_context(self._context_digest, self._feature_schema_digest)
        history: dict[str, list[float]] = {key: [] for key in self._bound_train}
        for observation in replay[-128:]:
            for key, value in observation.scenario_utilities.items():
                history[key].append(math.tanh(value / self.learning_policy.reward_scale))
        priorities = {}
        for key, values in history.items():
            if not values:
                continue
            recent = values[-16:]
            difficulty = sum(max(0.0, -value) for value in recent) / len(recent)
            progress = abs(sum(recent) / len(recent) - sum(values) / len(values))
            uncertainty = 1.0 / math.sqrt(len(values) + 1)
            priorities[key] = min(4.0, difficulty + progress + uncertainty)
        return MappingProxyType(priorities)

    def _learn_observation(self, observation: TrainingObservation, *, replay: Sequence[TrainingObservation]) -> None:
        model = self._predictor
        if model is None:
            raise MirrorRoomError("neural predictor is not bound")
        prediction, _ = model.predict(observation.features)
        target, _ = model.targets(observation)
        model.residual_variance = min(4.0, 0.95 * model.residual_variance + 0.05 * (target - prediction) ** 2)
        model.observations_seen += 1
        # Deterministic prioritized replay retains recent failures and useful
        # successes. A rotating uniform half keeps low-error samples represented.
        recent = tuple(replay[-64:])
        stride = max(1, len(replay) // 64)
        pool = tuple({item.training_report_digest: item for item in (*tuple(replay[::stride])[:64], *recent)}.values())
        for update in range(self.learning_policy.updates_per_observation):
            count = min(len(pool), self.learning_policy.replay_batch_size)
            half = max(1, count // 2)
            ranked = sorted(pool, key=lambda item: (-abs(model.targets(item)[0] - model.predict(item.features)[0]), item.training_report_digest))
            batch = list(ranked[:half])
            selected = {item.training_report_digest for item in batch}
            start = (model.observations_seen * self.learning_policy.updates_per_observation + update) % len(pool)
            for offset in range(len(pool)):
                item = pool[(start + offset) % len(pool)]
                if item.training_report_digest not in selected:
                    batch.append(item)
                    selected.add(item.training_report_digest)
                if len(batch) >= count:
                    break
            model.train_batch(batch)

    def _save_checkpoint(self) -> None:
        model, experiment, context = self._predictor, self._bound_experiment_id, self._context_digest
        if model is None or experiment is None or context is None:
            return
        prior = self.training_archive.checkpoint_for(context, self._feature_schema_digest, self.generator_id)
        checkpoint = LearnerCheckpoint(
            context_digest=context, feature_schema_digest=self._feature_schema_digest,
            generator_id=self.generator_id, experiment_id=experiment,
            architecture=model.architecture, weights=tuple(model.weights), optimizer_first=tuple(model.first), optimizer_second=tuple(model.second),
            training_steps=model.training_steps, observations_seen=model.observations_seen, rejected_updates=model.rejected_updates,
            residual_variance=model.residual_variance, step_sizes=self._steps,
            predecessor_digest=None if prior is None else prior.digest,
        )
        self.training_archive = self.training_archive.with_checkpoint(checkpoint)
        self._checkpoint_digest = checkpoint.digest

    @property
    def step_sizes(self) -> Mapping[str, float]:
        return MappingProxyType(dict(sorted(self._steps.items())))

    def _numeric_parent(
        self,
        feedback: LearningFeedback,
    ) -> dict[str, float]:
        values: dict[str, float] = {}
        for dimension in self.dimensions:
            raw = feedback.champion.parameters.get(dimension.name)
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise MirrorRoomError(
                    f"champion parameter is not numeric: {dimension.name}"
                )
            value = float(raw)
            if not math.isfinite(value):
                raise MirrorRoomError(
                    f"champion parameter is not finite: {dimension.name}"
                )
            if value < dimension.lower or value > dimension.upper:
                raise MirrorRoomError(
                    f"champion parameter exceeds search bounds: {dimension.name}"
                )
            values[dimension.name] = value
        return values

    def _adapt_steps(self, current: Mapping[str, float]) -> None:
        previous = self._last_parent_parameters
        if previous is None:
            return
        by_name = {item.name: item for item in self.dimensions}
        for name, current_value in current.items():
            dimension = by_name[name]
            changed = not math.isclose(
                current_value,
                previous[name],
                rel_tol=0.0,
                abs_tol=1e-15,
            )
            if changed:
                self._steps[name] = min(
                    dimension.max_step,
                    self._steps[name] * dimension.expansion,
                )
            else:
                self._steps[name] = max(
                    dimension.min_step,
                    self._steps[name] * dimension.contraction,
                )

    def propose(
        self,
        feedback: LearningFeedback,
        *,
        limit: int,
    ) -> Sequence[MirrorCandidate]:
        if not isinstance(feedback, LearningFeedback):
            raise TypeError("feedback must be LearningFeedback")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 512:
            raise MirrorRoomError("coordinate learner limit must be within 1..512")

        parent_numeric = self._numeric_parent(feedback)
        if self._context_digest is not None and self._pending_candidates:
            raise MirrorRoomError("previous numeric proposals require completed TRAIN outcomes before advancing")
        if self._context_digest is None:
            self._adapt_steps(parent_numeric)
        elif {item.digest for item in feedback.training_scenarios} != set(self._bound_train):
            raise MirrorRoomError("proposal feedback differs from the bound TRAIN corpus")

        replay = () if self._context_digest is None else self.training_archive.for_context(self._context_digest, self._feature_schema_digest)
        signals: dict[str, float] = {}
        strengths: dict[str, float] = {}
        for index, dimension in enumerate(self.dimensions):
            if self._context_digest is None:
                signals[dimension.name] = float(self.training_archive.preferred_direction(dimension.name))
                strengths[dimension.name] = self.training_archive.dimension_strength(dimension.name)
            else:
                signals[dimension.name] = sum((math.tanh(item.training_utility_delta / self.learning_policy.reward_scale) if item.guardrails_passed else -0.5) * item.features[4 * index + 2] for item in replay)
                strengths[dimension.name] = sum(abs(math.tanh(item.training_utility_delta / self.learning_policy.reward_scale) * item.features[4 * index + 2]) for item in replay)

        dimensions = tuple(
            sorted(
                self.dimensions,
                key=lambda item: (
                    -strengths[item.name],
                    item.name,
                ),
            )
        )
        start = (feedback.generation - 1) % len(dimensions)
        ordered = dimensions[start:] + dimensions[:start]
        base_parameters = dict(feedback.champion.parameters)

        pool: list[tuple[dict[str, object], str, str]] = []
        pool_fingerprints: set[str] = set()
        model = self._predictor
        warm = model is not None and model.observations_seen >= self.learning_policy.minimum_rank_observations
        scales = (1.0, 0.5, 2.0) if warm else (1.0,)
        for dimension in ordered:
            center = parent_numeric[dimension.name]
            directions = ((-1.0, "down"), (1.0, "up")) if signals[dimension.name] < 0 else ((1.0, "up"), (-1.0, "down"))
            for scale in scales:
                for direction, label in directions:
                    target = min(dimension.upper, max(dimension.lower, center + direction * self._steps[dimension.name] * scale))
                    if math.isclose(target, center, rel_tol=0.0, abs_tol=1e-15):
                        continue
                    parameters = dict(base_parameters)
                    parameters[dimension.name] = target
                    fingerprint = _digest(parameters)
                    if fingerprint in pool_fingerprints or fingerprint in self._proposed_parameters:
                        continue
                    pool_fingerprints.add(fingerprint)
                    pool.append((parameters, dimension.name, label))
                    if len(pool) >= self.learning_policy.max_candidate_pool:
                        break
                if len(pool) >= self.learning_policy.max_candidate_pool:
                    break
            if len(pool) >= self.learning_policy.max_candidate_pool:
                break
        # Mixed edits expose interactions between engine/editor dimensions,
        # while single-coordinate proposals remain available for attribution.
        if warm and len(ordered) > 1:
            for first_index in range(min(4, len(ordered))):
                first = ordered[first_index]
                second = ordered[(first_index + 1) % len(ordered)]
                parameters = dict(base_parameters)
                for dimension in (first, second):
                    direction = -1.0 if signals[dimension.name] < 0 else 1.0
                    parameters[dimension.name] = min(dimension.upper, max(dimension.lower, parent_numeric[dimension.name] + direction * self._steps[dimension.name]))
                fingerprint = _digest(parameters)
                if fingerprint not in pool_fingerprints and fingerprint not in self._proposed_parameters and len(pool) < self.learning_policy.max_candidate_pool:
                    pool_fingerprints.add(fingerprint)
                    pool.append((parameters, first.name, "mixed"))
        # A bounded low-discrepancy escape keeps a long campaign productive
        # after coordinate steps hit a boundary or repeat a local plateau.
        # Its parameters are still quarantined under the same hard bounds.
        if warm or not pool:
            for index, dimension in enumerate(ordered):
                if len(pool) >= self.learning_policy.max_candidate_pool:
                    break
                sequence = feedback.generation + 1 + index * 131
                fraction, divisor = 0.0, 1.0
                for _ in range(64):
                    if not sequence:
                        break
                    sequence, digit = divmod(sequence, 2)
                    divisor *= 2.0
                    fraction += digit / divisor
                parameters = dict(base_parameters)
                parameters[dimension.name] = min(dimension.upper, max(dimension.lower, dimension.lower + dimension.max_step * fraction))
                fingerprint = _digest(parameters)
                if fingerprint not in pool_fingerprints and fingerprint not in self._proposed_parameters:
                    pool_fingerprints.add(fingerprint)
                    pool.append((parameters, dimension.name, "explore"))
        if warm:
            pool = self._rank_pool(pool, parent=base_parameters, replay=replay, limit=limit)

        proposals: list[MirrorCandidate] = []
        ordinal = 0
        for parameters, dimension_name, label in pool[:limit]:
            ordinal += 1
            change_digest = _digest(
                {
                    "strategy_digest": self.strategy_digest,
                    "generation": feedback.generation,
                    "parent_behavior_digest": feedback.champion.behavior_digest,
                    "dimension": dimension_name,
                    "direction": label,
                    "parameters": parameters,
                }
            )
            dimension_label = dimension_name if len(dimension_name) <= 96 else f"{dimension_name[:64]}-{_digest(dimension_name)[:16]}"
            candidate_id = f"mirror-g{feedback.generation}-{ordinal}-{dimension_label}-{label}"
            proposals.append(
                MirrorCandidate(
                    candidate_id=candidate_id,
                    version=f"mirror-{feedback.generation}-{ordinal}",
                    producer_id=self.generator_id,
                    change_ref=f"mirror-search:{feedback.generation}:{ordinal}:{dimension_label}:{label}",
                    change_digest=change_digest,
                    parameters=parameters,
                    parent_candidate_id=feedback.champion.candidate_id,
                    evidence_refs=(f"mirror-feedback:{feedback.generation}",),
                )
            )
            self._proposed_parameters.add(_digest(parameters))
            if self._context_digest is not None:
                self._pending_candidates[proposals[-1].digest] = feedback.champion.digest

        self._last_parent_parameters = parent_numeric
        return tuple(proposals)

    def _rank_pool(self, pool: Sequence[tuple[dict[str, object], str, str]], *, parent: Mapping[str, object], replay: Sequence[TrainingObservation], limit: int) -> list[tuple[dict[str, object], str, str]]:
        model = self._predictor
        if model is None:
            return list(pool)
        # Bound inference work independently of accumulated run history.
        representatives = tuple(replay[-128:])
        ranked = []
        for ordinal, proposal in enumerate(pool):
            features = self._features(parent, proposal[0])
            reward, predicted_cost = model.predict(features)
            distances = [sum((left - right) ** 2 for left, right in zip(features, item.features, strict=True)) / len(features) for item in representatives]
            nearest = min(distances, default=1.0)
            effective_visits = sum(math.exp(-distance * 8.0) for distance in distances)
            uncertainty = min(2.0, math.sqrt(model.residual_variance + nearest) * math.sqrt(math.log(model.observations_seen + 2.0) / (effective_visits + 1.0)))
            score = reward + self.learning_policy.uncertainty_bonus * uncertainty - self.learning_policy.cost_penalty * max(0.0, predicted_cost)
            ranked.append((score, ordinal, features, proposal))
        result = []
        diversity_by_ordinal: dict[int, float] = {}
        while ranked and len(result) < limit:
            def score(row: tuple[float, int, tuple[float, ...], tuple[dict[str, object], str, str]]) -> tuple[float, int]:
                return row[0] + self.learning_policy.diversity_bonus * diversity_by_ordinal.get(row[1], 0.0), -row[1]
            best = max(range(len(ranked)), key=lambda index: score(ranked[index]))
            _, _, features, proposal = ranked.pop(best)
            result.append(proposal)
            # Incremental nearest-selected distance avoids re-scanning every
            # already selected feature vector for each remaining proposal.
            for _, ordinal, remaining_features, _ in ranked:
                distance = math.sqrt(sum((left - right) ** 2 for left, right in zip(remaining_features, features, strict=True)) / len(features))
                diversity_by_ordinal[ordinal] = min(diversity_by_ordinal.get(ordinal, float("inf")), distance)
        return result


__all__ = [
    "AdaptiveLearningPolicy",
    "DeterministicCoordinateLearner",
    "NumericDimension",
]

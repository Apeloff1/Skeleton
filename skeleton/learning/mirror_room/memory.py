"""TRAIN-only cross-run learning memory for Mirror Room.

The archive keeps TRAIN-selected lessons, completed positive/negative numeric
observations, and bounded versioned candidate-ranker optimizer checkpoints.
Validation qualification, sealed holdout results, promotion evidence, and
production authority are never serialized into this memory.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from collections import deque
import math
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

from .contracts import (
    MirrorRoomError,
    ScenarioSplit,
    _digest,
    _finite,
    _non_negative_int,
    _positive_int,
    _sha256,
    _text,
    _token,
)


MAX_TRAINING_REPLAY = 2048
MAX_LEARNER_CHECKPOINTS = 32
MAX_REPLAY_FEATURE_VALUES = 524288
MAX_REPLAY_SCENARIO_VALUES = 65536
MAX_TRAINING_LESSONS = 8192


@dataclass(frozen=True, slots=True)
class TrainingObservation:
    """A completed TRAIN comparison, including unsuccessful proposals.

    Features are normalized numeric edits, never prompts, validation scores,
    or production permissions. The context binds the evaluator, metric policy,
    fixed TRAIN corpus and feature schema before the first proposal.
    """

    context_digest: str
    feature_schema_digest: str
    experiment_id: str
    run_id: str
    generation: int
    parent_behavior_digest: str
    candidate_behavior_digest: str
    candidate_id: str
    training_report_digest: str
    scenario_digests: tuple[str, ...]
    features: tuple[float, ...]
    training_utility_delta: float
    cost_units: float
    guardrails_passed: bool
    scenario_utilities: Mapping[str, float]

    def __post_init__(self) -> None:
        for name in (
            "context_digest", "feature_schema_digest", "parent_behavior_digest",
            "candidate_behavior_digest", "training_report_digest",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        for name in ("experiment_id", "candidate_id"):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        object.__setattr__(self, "run_id", _text("run_id", self.run_id))
        object.__setattr__(self, "generation", _positive_int("generation", self.generation))
        scenarios = tuple(sorted(_sha256("scenario_digest", item) for item in self.scenario_digests))
        if not scenarios or len(scenarios) > 4096 or len(scenarios) != len(set(scenarios)):
            raise MirrorRoomError("training observation requires unique bounded scenarios")
        object.__setattr__(self, "scenario_digests", scenarios)
        features = tuple(_finite("training feature", item) for item in self.features)
        if not features or len(features) > 512 or any(abs(item) > 8.0 for item in features):
            raise MirrorRoomError("training feature vector exceeds normalized envelope")
        object.__setattr__(self, "features", features)
        object.__setattr__(self, "training_utility_delta", _finite("training_utility_delta", self.training_utility_delta))
        object.__setattr__(self, "cost_units", _finite("cost_units", self.cost_units, minimum=0.0))
        if not isinstance(self.guardrails_passed, bool):
            raise MirrorRoomError("guardrails_passed must be boolean")
        if not isinstance(self.scenario_utilities, Mapping):
            raise MirrorRoomError("scenario_utilities must be a mapping")
        utilities = {
            _sha256("scenario utility digest", key): _finite("scenario utility", value)
            for key, value in self.scenario_utilities.items()
        }
        if set(utilities) != set(scenarios):
            raise MirrorRoomError("training utility scenarios do not match fixed corpus")
        object.__setattr__(self, "scenario_utilities", MappingProxyType(dict(sorted(utilities.items()))))

    @property
    def identity(self) -> tuple[str, str, int, str]:
        return self.context_digest, self.run_id, self.generation, self.candidate_id

    def payload(self) -> dict[str, object]:
        return {
            "context_digest": self.context_digest,
            "feature_schema_digest": self.feature_schema_digest,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "generation": self.generation,
            "parent_behavior_digest": self.parent_behavior_digest,
            "candidate_behavior_digest": self.candidate_behavior_digest,
            "candidate_id": self.candidate_id,
            "training_report_digest": self.training_report_digest,
            "scenario_digests": list(self.scenario_digests),
            "features": list(self.features),
            "training_utility_delta": self.training_utility_delta,
            "cost_units": self.cost_units,
            "guardrails_passed": self.guardrails_passed,
            "scenario_utilities": dict(self.scenario_utilities),
            "evidence_plane": "train", "production_authority": False,
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class LearnerCheckpoint:
    """Versioned candidate-ranking weights and exact Adam continuation state.

    These weights select sandbox experiments. They cannot become language-model
    weights, grant promotion, or replace any quality threshold.
    """

    context_digest: str
    feature_schema_digest: str
    generator_id: str
    experiment_id: str
    architecture: tuple[int, ...]
    weights: tuple[float, ...]
    optimizer_first: tuple[float, ...]
    optimizer_second: tuple[float, ...]
    training_steps: int
    observations_seen: int
    rejected_updates: int
    residual_variance: float
    step_sizes: Mapping[str, float]
    predecessor_digest: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise MirrorRoomError("unsupported learner checkpoint version")
        for name in ("context_digest", "feature_schema_digest"):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        for name in ("generator_id", "experiment_id"):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        if self.predecessor_digest is not None:
            object.__setattr__(self, "predecessor_digest", _sha256("predecessor_digest", self.predecessor_digest))
        architecture = tuple(_positive_int("layer width", value) for value in self.architecture)
        if len(architecture) != 4 or architecture[0] > 512 or architecture[1:] != (16, 8, 2):
            raise MirrorRoomError("learner architecture exceeds declared bounded network")
        object.__setattr__(self, "architecture", architecture)
        count = sum((left + 1) * right for left, right in zip(architecture, architecture[1:]))
        for name in ("weights", "optimizer_first", "optimizer_second"):
            values = tuple(_finite(name, value) for value in getattr(self, name))
            if len(values) != count or any(abs(value) > 1e6 for value in values):
                raise MirrorRoomError("checkpoint tensor shape or finite envelope mismatch")
            if name == "optimizer_second" and any(value < 0 for value in values):
                raise MirrorRoomError("Adam second moments cannot be negative")
            object.__setattr__(self, name, values)
        for name in ("training_steps", "observations_seen", "rejected_updates"):
            object.__setattr__(self, name, _non_negative_int(name, getattr(self, name)))
        variance = _finite("residual_variance", self.residual_variance, minimum=0.0)
        if variance > 4.0:
            raise MirrorRoomError("normalized residual variance exceeds envelope")
        object.__setattr__(self, "residual_variance", variance)
        if not isinstance(self.step_sizes, Mapping) or not self.step_sizes or len(self.step_sizes) > 64:
            raise MirrorRoomError("checkpoint step sizes must be a bounded mapping")
        steps = {_token("dimension", key): _finite("step size", value, minimum=0.0) for key, value in self.step_sizes.items()}
        if any(value <= 0.0 for value in steps.values()):
            raise MirrorRoomError("checkpoint step sizes must be positive")
        object.__setattr__(self, "step_sizes", MappingProxyType(dict(sorted(steps.items()))))

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "context_digest": self.context_digest,
            "feature_schema_digest": self.feature_schema_digest,
            "generator_id": self.generator_id,
            "experiment_id": self.experiment_id,
            "architecture": list(self.architecture),
            "weights": list(self.weights),
            "optimizer_first": list(self.optimizer_first),
            "optimizer_second": list(self.optimizer_second),
            "training_steps": self.training_steps,
            "observations_seen": self.observations_seen,
            "rejected_updates": self.rejected_updates,
            "residual_variance": self.residual_variance,
            "step_sizes": dict(self.step_sizes),
            "predecessor_digest": self.predecessor_digest,
            "evidence_plane": "train", "production_authority": False,
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class TrainingLesson:
    """Reusable experience derived solely from one TRAIN-selected transition."""

    experiment_id: str
    run_id: str
    generation: int
    parent_candidate_id: str
    candidate_id: str
    parent_behavior_digest: str
    candidate_behavior_digest: str
    changed_parameters: tuple[str, ...]
    numeric_deltas: Mapping[str, float]
    training_report_digest: str
    training_utility_delta: float
    hard_example_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "experiment_id",
            _token("experiment_id", self.experiment_id),
        )
        object.__setattr__(self, "run_id", _text("run_id", self.run_id))
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation <= 0
        ):
            raise MirrorRoomError("training lesson generation must be positive")
        for field in ("parent_candidate_id", "candidate_id"):
            object.__setattr__(
                self,
                field,
                _token(field, getattr(self, field)),
            )
        for field in (
            "parent_behavior_digest",
            "candidate_behavior_digest",
            "training_report_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(field, getattr(self, field)),
            )
        changed = tuple(
            sorted(
                {
                    _token("changed_parameter", item)
                    for item in self.changed_parameters
                }
            )
        )
        object.__setattr__(self, "changed_parameters", changed)
        if not isinstance(self.numeric_deltas, Mapping):
            raise MirrorRoomError("numeric_deltas must be a mapping")
        deltas = {}
        for key, value in self.numeric_deltas.items():
            token = _token("numeric_delta", key)
            delta = _finite(f"numeric_deltas[{token}]", value)
            if math.isclose(delta, 0.0, rel_tol=0.0, abs_tol=1e-15):
                raise MirrorRoomError("numeric training delta cannot be zero")
            if token not in changed:
                raise MirrorRoomError(
                    "numeric delta must identify a changed parameter"
                )
            deltas[token] = delta
        object.__setattr__(
            self,
            "numeric_deltas",
            MappingProxyType(dict(sorted(deltas.items()))),
        )
        object.__setattr__(
            self,
            "training_utility_delta",
            _finite(
                "training_utility_delta",
                self.training_utility_delta,
            ),
        )
        object.__setattr__(
            self,
            "hard_example_digests",
            tuple(
                sorted(
                    {
                        _sha256("hard_example_digest", item)
                        for item in self.hard_example_digests
                    }
                )
            ),
        )

    def payload(self) -> dict[str, object]:
        return {
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "generation": self.generation,
            "parent_candidate_id": self.parent_candidate_id,
            "candidate_id": self.candidate_id,
            "parent_behavior_digest": self.parent_behavior_digest,
            "candidate_behavior_digest": self.candidate_behavior_digest,
            "changed_parameters": list(self.changed_parameters),
            "numeric_deltas": dict(self.numeric_deltas),
            "training_report_digest": self.training_report_digest,
            "training_utility_delta": self.training_utility_delta,
            "hard_example_digests": list(self.hard_example_digests),
            "evidence_plane": "train",
            "production_authority": False,
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


def _hard_example_digest(item: object) -> str:
    return _digest(
        {
            "scenario_id": getattr(item, "scenario_id"),
            "scenario_digest": getattr(item, "scenario_digest"),
            "difficulty": getattr(item, "difficulty"),
            "metric_deltas": dict(getattr(item, "metric_deltas")),
        }
    )


def _numeric_delta(parent: object, candidate: object) -> tuple[
    tuple[str, ...],
    Mapping[str, float],
]:
    parent_parameters = dict(getattr(parent, "parameters"))
    candidate_parameters = dict(getattr(candidate, "parameters"))
    changed: list[str] = []
    numeric: dict[str, float] = {}
    for name in sorted(set(parent_parameters) | set(candidate_parameters)):
        before = parent_parameters.get(name)
        after = candidate_parameters.get(name)
        if before == after:
            continue
        changed.append(_token("changed_parameter", name))
        if (
            not isinstance(before, bool)
            and not isinstance(after, bool)
            and isinstance(before, (int, float))
            and isinstance(after, (int, float))
        ):
            delta = float(after) - float(before)
            if math.isfinite(delta) and not math.isclose(
                delta,
                0.0,
                rel_tol=0.0,
                abs_tol=1e-15,
            ):
                numeric[name] = delta
    return tuple(changed), MappingProxyType(dict(sorted(numeric.items())))


@dataclass(frozen=True, slots=True)
class TrainingLearningArchive:
    """Canonical TRAIN-only memory reusable by future Mirror Room learners."""

    lessons: tuple[TrainingLesson, ...] = ()
    observations: tuple[TrainingObservation, ...] = ()
    checkpoints: tuple[LearnerCheckpoint, ...] = ()

    def __post_init__(self) -> None:
        rows = tuple(self.lessons)
        if len(rows) > MAX_TRAINING_LESSONS or any(not isinstance(item, TrainingLesson) for item in rows):
            raise MirrorRoomError(
                "training archive must contain TrainingLesson values"
            )
        ordered = tuple(
            sorted(
                rows,
                key=lambda item: (
                    item.experiment_id,
                    item.run_id,
                    item.generation,
                    item.candidate_id,
                    item.digest,
                ),
            )
        )
        keys = [
            (
                item.experiment_id,
                item.run_id,
                item.generation,
                item.candidate_id,
            )
            for item in ordered
        ]
        if len(keys) != len(set(keys)):
            raise MirrorRoomError("training archive lesson identity reused")
        object.__setattr__(self, "lessons", ordered)
        observations = tuple(self.observations)
        if len(observations) > MAX_TRAINING_REPLAY or any(not isinstance(item, TrainingObservation) for item in observations):
            raise MirrorRoomError("training replay exceeds its bounded typed envelope")
        if sum(len(item.features) for item in observations) > MAX_REPLAY_FEATURE_VALUES or sum(len(item.scenario_digests) for item in observations) > MAX_REPLAY_SCENARIO_VALUES:
            raise MirrorRoomError("training replay exceeds its feature or scenario memory ceiling")
        identities = [item.identity for item in observations]
        reports = [item.training_report_digest for item in observations]
        if len(identities) != len(set(identities)) or len(reports) != len(set(reports)):
            raise MirrorRoomError("training replay contains duplicate outcome identities")
        object.__setattr__(self, "observations", observations)
        checkpoints = tuple(self.checkpoints)
        if len(checkpoints) > MAX_LEARNER_CHECKPOINTS or any(not isinstance(item, LearnerCheckpoint) for item in checkpoints):
            raise MirrorRoomError("learner checkpoints exceed their bounded typed envelope")
        checkpoint_keys = [(item.context_digest, item.feature_schema_digest, item.generator_id) for item in checkpoints]
        if len(checkpoint_keys) != len(set(checkpoint_keys)):
            raise MirrorRoomError("archive contains multiple current checkpoints for one learner context")
        object.__setattr__(self, "checkpoints", checkpoints)

    def with_observation(self, observation: TrainingObservation) -> "TrainingLearningArchive":
        """Append one verified outcome; exact redelivery is idempotent."""

        if not isinstance(observation, TrainingObservation):
            raise TypeError("observation must be TrainingObservation")
        for existing in self.observations:
            if existing.identity == observation.identity or existing.training_report_digest == observation.training_report_digest:
                if existing.digest != observation.digest:
                    raise MirrorRoomError("training outcome identity was reused with different evidence")
                return self
        retained = list((*self.observations, observation)[-MAX_TRAINING_REPLAY:])
        feature_count = sum(len(item.features) for item in retained)
        scenario_count = sum(len(item.scenario_digests) for item in retained)
        while feature_count > MAX_REPLAY_FEATURE_VALUES or scenario_count > MAX_REPLAY_SCENARIO_VALUES:
            removed = retained.pop(0)
            feature_count -= len(removed.features)
            scenario_count -= len(removed.scenario_digests)
        return replace(self, observations=tuple(retained))

    def with_checkpoint(self, checkpoint: LearnerCheckpoint) -> "TrainingLearningArchive":
        if not isinstance(checkpoint, LearnerCheckpoint):
            raise TypeError("checkpoint must be LearnerCheckpoint")
        key = checkpoint.context_digest, checkpoint.feature_schema_digest, checkpoint.generator_id
        retained = []
        for prior in self.checkpoints:
            prior_key = prior.context_digest, prior.feature_schema_digest, prior.generator_id
            if prior_key != key:
                retained.append(prior)
                continue
            if prior.digest == checkpoint.digest:
                return self
            if checkpoint.predecessor_digest != prior.digest:
                raise MirrorRoomError("learner checkpoint lineage does not extend current checkpoint")
            if checkpoint.training_steps < prior.training_steps or checkpoint.observations_seen < prior.observations_seen:
                raise MirrorRoomError("learner checkpoint counters cannot move backwards")
        return replace(self, checkpoints=tuple((*retained, checkpoint)[-MAX_LEARNER_CHECKPOINTS:]))

    def checkpoint_for(self, context_digest: str, feature_schema_digest: str, generator_id: str) -> LearnerCheckpoint | None:
        return next((item for item in self.checkpoints if (
            item.context_digest == context_digest
            and item.feature_schema_digest == feature_schema_digest
            and item.generator_id == generator_id
        )), None)

    @classmethod
    def from_runs(
        cls,
        runs: Iterable[object],
    ) -> "TrainingLearningArchive":
        """Extract only TRAIN-selected transitions from immutable run receipts."""

        from .engine import MirrorRunReceipt

        lessons: deque[TrainingLesson] = deque(maxlen=MAX_TRAINING_LESSONS)
        archive = cls()
        for run in runs:
            if not isinstance(run, MirrorRunReceipt):
                raise TypeError("archive source must be MirrorRunReceipt")
            for observation in run.training_archive.observations:
                archive = archive.with_observation(observation)
            for checkpoint in run.training_archive.checkpoints:
                prior = archive.checkpoint_for(checkpoint.context_digest, checkpoint.feature_schema_digest, checkpoint.generator_id)
                if prior is None or checkpoint.observations_seen > prior.observations_seen:
                    # A run may contain a compacted checkpoint chain. Exact
                    # receipt ancestry is retained in its predecessor digest;
                    # do not invent an intermediate optimizer transition.
                    remaining = tuple(item for item in archive.checkpoints if item is not prior)
                    archive = replace(archive, checkpoints=(*remaining, checkpoint)[-MAX_LEARNER_CHECKPOINTS:])
                elif checkpoint.observations_seen == prior.observations_seen and checkpoint.digest != prior.digest:
                    raise MirrorRoomError("divergent learner checkpoints at the same observation count")
            known = {
                run.production_baseline.candidate_id:
                run.production_baseline
            }
            for generation in sorted(
                run.generations,
                key=lambda item: item.generation,
            ):
                parent = known.get(generation.incoming_champion_id)
                if parent is None:
                    raise MirrorRoomError(
                        "training archive learner lineage is incomplete"
                    )
                selected = [
                    item
                    for item in generation.evaluations
                    if item.selected_for_learning
                ]
                if len(selected) > 1:
                    raise MirrorRoomError(
                        "multiple TRAIN learner champions in one generation"
                    )
                if not selected:
                    if (
                        generation.learning_champion_id
                        != parent.candidate_id
                    ):
                        raise MirrorRoomError(
                            "TRAIN learner champion changed without evidence"
                        )
                    continue

                evaluation = selected[0]
                report = evaluation.training_report
                candidate = evaluation.candidate
                if report.split is not ScenarioSplit.TRAIN:
                    raise MirrorRoomError(
                        "cross-run memory accepts TRAIN reports only"
                    )
                if (
                    report.baseline_candidate_id
                    != parent.candidate_id
                    or report.baseline_candidate_digest
                    != parent.digest
                ):
                    raise MirrorRoomError(
                        "training archive baseline lineage mismatch"
                    )
                if (
                    report.candidate_id != candidate.candidate_id
                    or report.candidate_digest != candidate.digest
                ):
                    raise MirrorRoomError(
                        "training archive candidate lineage mismatch"
                    )
                if (
                    generation.learning_champion_id
                    != candidate.candidate_id
                ):
                    raise MirrorRoomError(
                        "TRAIN selection does not match learner champion"
                    )
                changed, numeric = _numeric_delta(parent, candidate)
                lessons.append(
                    TrainingLesson(
                        experiment_id=run.experiment_id,
                        run_id=run.run_id,
                        generation=generation.generation,
                        parent_candidate_id=parent.candidate_id,
                        candidate_id=candidate.candidate_id,
                        parent_behavior_digest=parent.behavior_digest,
                        candidate_behavior_digest=(
                            candidate.behavior_digest
                        ),
                        changed_parameters=changed,
                        numeric_deltas=numeric,
                        training_report_digest=report.digest,
                        training_utility_delta=(
                            report.weighted_utility_delta
                        ),
                        hard_example_digests=tuple(
                            _hard_example_digest(item)
                            for item in generation.hard_examples
                        ),
                    )
                )
                known[candidate.candidate_id] = candidate
        return cls(tuple(lessons), archive.observations, archive.checkpoints)

    def for_experiment(
        self,
        experiment_id: str,
    ) -> "TrainingLearningArchive":
        target = _token("experiment_id", experiment_id)
        return TrainingLearningArchive(
            tuple(
                item
                for item in self.lessons
                if item.experiment_id == target
            ),
            tuple(item for item in self.observations if item.experiment_id == target),
            tuple(item for item in self.checkpoints if item.experiment_id == target),
        )

    def for_context(self, context_digest: str, feature_schema_digest: str) -> tuple[TrainingObservation, ...]:
        context = _sha256("context_digest", context_digest)
        features = _sha256("feature_schema_digest", feature_schema_digest)
        return tuple(item for item in self.observations if item.context_digest == context and item.feature_schema_digest == features)

    def dimension_strength(self, name: str) -> float:
        target = _token("dimension name", name)
        return sum(
            max(0.0, item.training_utility_delta)
            * abs(item.numeric_deltas.get(target, 0.0))
            for item in self.lessons
        )

    def preferred_direction(self, name: str) -> int:
        target = _token("dimension name", name)
        signal = sum(
            max(0.0, item.training_utility_delta)
            * item.numeric_deltas.get(target, 0.0)
            for item in self.lessons
        )
        if signal > 1e-15:
            return 1
        if signal < -1e-15:
            return -1
        return 0

    def suggested_step(self, name: str, fallback: float) -> float:
        target = _token("dimension name", name)
        default = _finite("fallback step", fallback, minimum=0.0)
        weighted = []
        for item in self.lessons:
            delta = item.numeric_deltas.get(target)
            weight = max(0.0, item.training_utility_delta)
            if delta is not None and weight > 0.0:
                weighted.append((abs(delta), weight))
        if not weighted:
            return default
        total_weight = sum(weight for _, weight in weighted)
        return sum(
            value * weight
            for value, weight in weighted
        ) / total_weight

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": 2,
            "evidence_plane": "train",
            "lessons": [item.payload() for item in self.lessons],
            "observations": [item.payload() for item in self.observations],
            "checkpoints": [item.payload() for item in self.checkpoints],
            "production_authority": False,
            "contains_validation_evidence": False,
            "contains_holdout_evidence": False,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object], *, expected_digest: str | None = None) -> "TrainingLearningArchive":
        """Restore through the existing archive owner, without pickle or code."""

        if not isinstance(payload, Mapping):
            raise MirrorRoomError("training archive payload must be a mapping")
        version = payload.get("schema_version")
        if not isinstance(version, int) or isinstance(version, bool) or version not in (1, 2):
            raise MirrorRoomError("unsupported training archive schema version")
        if payload.get("evidence_plane") != "train" or payload.get("production_authority") is not False:
            raise MirrorRoomError("training archive authority or evidence plane mismatch")
        if payload.get("contains_validation_evidence") is not False or payload.get("contains_holdout_evidence") is not False:
            raise MirrorRoomError("training archive cannot import qualification evidence")
        if expected_digest is not None and _digest(dict(payload)) != _sha256("archive digest", expected_digest):
            raise MirrorRoomError("training archive content digest mismatch")
        fields = {
            "lessons": TrainingLesson,
            "observations": TrainingObservation,
            "checkpoints": LearnerCheckpoint,
        }
        restored: dict[str, tuple[object, ...]] = {}
        for name, record_type in fields.items():
            raw = payload.get(name, ())
            if not isinstance(raw, (tuple, list)) or len(raw) > (MAX_TRAINING_REPLAY if name == "observations" else MAX_LEARNER_CHECKPOINTS if name == "checkpoints" else MAX_TRAINING_LESSONS):
                raise MirrorRoomError("training archive records exceed their envelope")
            records = []
            for row in raw:
                if not isinstance(row, Mapping) or row.get("evidence_plane") != "train" or row.get("production_authority") is not False:
                    raise MirrorRoomError("training archive record authority mismatch")
                values = {key: value for key, value in row.items() if key not in {"evidence_plane", "production_authority"}}
                try:
                    records.append(record_type(**values))
                except (TypeError, ValueError) as exc:
                    raise MirrorRoomError("malformed training archive record") from exc
            restored[name] = tuple(records)
        allowed = {"schema_version", "evidence_plane", "lessons", "production_authority", "contains_validation_evidence", "contains_holdout_evidence"}
        if version == 2:
            allowed |= {"observations", "checkpoints"}
        if set(payload) != allowed:
            raise MirrorRoomError("training archive fields do not match declared schema")
        return cls(**restored)

    @property
    def digest(self) -> str:
        return _digest(self.payload())


__all__ = [
    "LearnerCheckpoint",
    "MAX_LEARNER_CHECKPOINTS",
    "MAX_TRAINING_REPLAY",
    "TrainingLearningArchive",
    "TrainingLesson",
    "TrainingObservation",
]

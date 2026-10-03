"""TRAIN-only cross-run learning memory for Mirror Room.

The archive deliberately extracts only evidence that influenced the adaptive
TRAIN learner. Validation qualification, sealed holdout results, promotion
evidence, and production authority are never serialized into this memory.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

from .contracts import (
    MirrorRoomError,
    ScenarioSplit,
    _digest,
    _finite,
    _sha256,
    _text,
    _token,
)


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

    def __post_init__(self) -> None:
        rows = tuple(self.lessons)
        if any(not isinstance(item, TrainingLesson) for item in rows):
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

    @classmethod
    def from_runs(
        cls,
        runs: Iterable[object],
    ) -> "TrainingLearningArchive":
        """Extract only TRAIN-selected transitions from immutable run receipts."""

        from .engine import MirrorRunReceipt

        lessons: list[TrainingLesson] = []
        for run in runs:
            if not isinstance(run, MirrorRunReceipt):
                raise TypeError("archive source must be MirrorRunReceipt")
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
        return cls(tuple(lessons))

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
            )
        )

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
            "schema_version": 1,
            "evidence_plane": "train",
            "lessons": [item.payload() for item in self.lessons],
            "production_authority": False,
            "contains_validation_evidence": False,
            "contains_holdout_evidence": False,
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


__all__ = [
    "TrainingLearningArchive",
    "TrainingLesson",
]

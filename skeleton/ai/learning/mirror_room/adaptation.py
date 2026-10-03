"""Deterministic bounded adaptation strategies for Mirror Room.

This module provides a provider-neutral reference learner so callers can run a
real adaptive search without implementing a custom CandidateGenerator. It is
intentionally conservative: it operates only on explicitly declared numeric
dimensions, stays inside hard bounds, and derives every proposal solely from
TRAIN-visible LearningFeedback.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Mapping, Sequence

from .contracts import (
    LearningFeedback,
    MirrorCandidate,
    MirrorRoomError,
    _digest,
    _finite,
    _token,
)
from .memory import TrainingLearningArchive


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
        if upper <= lower:
            raise MirrorRoomError("numeric dimension upper must exceed lower")
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
    """Bounded derivative-free learner over explicit numeric parameters.

    The learner performs deterministic coordinate search around the current
    TRAIN-selected champion. On the next generation it expands coordinates that
    changed in the learner champion and contracts coordinates that did not.
    This gives Mirror Room a functional built-in adaptation path while keeping
    validation and holdout completely outside the proposal interface.
    """

    def __init__(
        self,
        *,
        generator_id: str,
        dimensions: Sequence[NumericDimension],
        training_archive: TrainingLearningArchive | None = None,
    ) -> None:
        self.generator_id = _token("generator_id", generator_id)
        rows = tuple(dimensions)
        if not rows:
            raise MirrorRoomError("coordinate learner requires dimensions")
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

    @property
    def strategy_digest(self) -> str:
        return _digest(
            {
                "generator_id": self.generator_id,
                "dimensions": [item.digest for item in self.dimensions],
                "training_archive_digest": self.training_archive.digest,
            }
        )

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
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise MirrorRoomError("coordinate learner limit must be positive")

        parent_numeric = self._numeric_parent(feedback)
        self._adapt_steps(parent_numeric)

        dimensions = tuple(
            sorted(
                self.dimensions,
                key=lambda item: (
                    -self.training_archive.dimension_strength(item.name),
                    item.name,
                ),
            )
        )
        start = (feedback.generation - 1) % len(dimensions)
        ordered = dimensions[start:] + dimensions[:start]
        base_parameters = dict(feedback.champion.parameters)

        proposals: list[MirrorCandidate] = []
        ordinal = 0
        for dimension in ordered:
            center = parent_numeric[dimension.name]
            step = self._steps[dimension.name]
            remembered_direction = (
                self.training_archive.preferred_direction(
                    dimension.name
                )
            )
            directions = (
                ((-1.0, "down"), (1.0, "up"))
                if remembered_direction < 0
                else ((1.0, "up"), (-1.0, "down"))
            )
            for direction, label in directions:
                target = min(
                    dimension.upper,
                    max(
                        dimension.lower,
                        center + direction * step,
                    ),
                )
                if math.isclose(
                    target,
                    center,
                    rel_tol=0.0,
                    abs_tol=1e-15,
                ):
                    continue
                ordinal += 1
                parameters = dict(base_parameters)
                parameters[dimension.name] = target
                change_digest = _digest(
                    {
                        "strategy_digest": self.strategy_digest,
                        "generation": feedback.generation,
                        "parent_behavior_digest": (
                            feedback.champion.behavior_digest
                        ),
                        "dimension": dimension.name,
                        "direction": label,
                        "parameters": parameters,
                    }
                )
                candidate_id = (
                    f"mirror-g{feedback.generation}-"
                    f"{ordinal}-{dimension.name}-{label}"
                )
                proposals.append(
                    MirrorCandidate(
                        candidate_id=candidate_id,
                        version=(
                            f"mirror-{feedback.generation}-{ordinal}"
                        ),
                        producer_id=self.generator_id,
                        change_ref=(
                            f"mirror-search:{feedback.generation}:"
                            f"{ordinal}:{dimension.name}:{label}"
                        ),
                        change_digest=change_digest,
                        parameters=parameters,
                        parent_candidate_id=(
                            feedback.champion.candidate_id
                        ),
                        evidence_refs=(
                            f"mirror-feedback:{feedback.generation}",
                        ),
                    )
                )
                if len(proposals) >= limit:
                    self._last_parent_parameters = parent_numeric
                    return tuple(proposals)

        self._last_parent_parameters = parent_numeric
        return tuple(proposals)


__all__ = [
    "DeterministicCoordinateLearner",
    "NumericDimension",
]

"""Non-compensable P2 quality-vector evaluation.

This module intentionally has no weighted aggregate score. A required quality
dimension either passes with evidence or blocks qualification.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


class P2QualityError(RuntimeError):
    pass


def _text(value: str, field: str, *, maximum: int = 2048) -> str:
    text = str(value).strip()
    if not text or len(text) > maximum:
        raise ValueError(f"{field} must be non-empty bounded text")
    return text


@dataclass(frozen=True, slots=True)
class QualityObservation:
    dimension_id: str
    passed: bool
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "dimension_id",
            _text(self.dimension_id, "dimension_id", maximum=192),
        )
        if not isinstance(self.passed, bool):
            raise TypeError("passed must be boolean")
        refs = tuple(_text(item, "evidence_ref") for item in self.evidence_refs)
        if not refs:
            raise ValueError("quality observation requires evidence")
        if len(refs) != len(set(refs)):
            raise ValueError("quality evidence refs must be unique")
        object.__setattr__(self, "evidence_refs", refs)


@dataclass(frozen=True, slots=True)
class QualityVectorResult:
    state: str
    failed_dimensions: tuple[str, ...]
    missing_dimensions: tuple[str, ...]
    evidence_refs: tuple[str, ...]


def evaluate_quality_vector(
    required_dimensions: Iterable[str],
    observations: Iterable[QualityObservation],
) -> QualityVectorResult:
    required = tuple(sorted({_text(x, "required_dimension", maximum=192) for x in required_dimensions}))
    if not required:
        raise P2QualityError("quality vector requires at least one dimension")

    by_id: dict[str, QualityObservation] = {}
    evidence: set[str] = set()
    for observation in observations:
        if not isinstance(observation, QualityObservation):
            raise TypeError("observations must contain QualityObservation")
        if observation.dimension_id in by_id:
            raise P2QualityError(
                f"duplicate quality observation: {observation.dimension_id}"
            )
        by_id[observation.dimension_id] = observation
        evidence.update(observation.evidence_refs)

    unknown = sorted(set(by_id) - set(required))
    if unknown:
        raise P2QualityError(f"unexpected quality dimensions: {unknown}")

    missing = tuple(sorted(set(required) - set(by_id)))
    failed = tuple(
        sorted(
            dimension
            for dimension, observation in by_id.items()
            if observation.passed is False
        )
    )
    if failed or missing:
        state = "blocked"
    else:
        state = "passed"

    return QualityVectorResult(
        state=state,
        failed_dimensions=failed,
        missing_dimensions=missing,
        evidence_refs=tuple(sorted(evidence)),
    )


__all__ = [
    "P2QualityError",
    "QualityObservation",
    "QualityVectorResult",
    "evaluate_quality_vector",
]

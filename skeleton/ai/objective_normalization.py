"""Ambiguity-preserving objective normalization for VOL-302."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import unicodedata
from typing import Any, Iterable

from skeleton.contracts.canonical import canonical_json_bytes


class ObjectiveAmbiguity(str, Enum):
    NONE = "none"
    LOW_IMPACT = "low_impact"
    HIGH_IMPACT = "high_impact"


@dataclass(frozen=True, order=True)
class ObjectiveAssumption:
    key: str
    interpretation: str
    source: str

    def __post_init__(self) -> None:
        if not self.key or self.key.strip() != self.key or not self.key.isascii():
            raise ValueError("assumption key must be canonical ASCII")
        for value in (self.interpretation, self.source):
            if not value or value.strip() != value:
                raise ValueError("assumption interpretation and source must be explicit")


@dataclass(frozen=True)
class NormalizedObjective:
    original: str
    canonical: str
    assumptions: tuple[ObjectiveAssumption, ...]
    ambiguity: ObjectiveAmbiguity
    bounded_alternatives: tuple[str, ...] = ()
    clarification_required: bool = False

    def __post_init__(self) -> None:
        if not self.original or not self.canonical:
            raise ValueError("objective text cannot be empty")
        if self.canonical != unicodedata.normalize("NFKC", self.canonical):
            raise ValueError("canonical objective must be NFKC")
        keys = [a.key for a in self.assumptions]
        if len(keys) != len(set(keys)):
            raise ValueError("assumption keys must be unique")
        alternatives = self.bounded_alternatives
        if len(alternatives) > 3:
            raise ValueError("bounded alternatives are limited to three")
        if any(not value or value.strip() != value for value in alternatives):
            raise ValueError("alternatives must be explicit")
        if len(set(alternatives)) != len(alternatives):
            raise ValueError("alternatives must be unique")
        if self.ambiguity is ObjectiveAmbiguity.HIGH_IMPACT:
            if not self.clarification_required and not alternatives:
                raise ValueError("high-impact ambiguity requires clarification or bounded alternatives")
        elif self.clarification_required:
            raise ValueError("clarification flag is reserved for high-impact ambiguity")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "canonical": self.canonical,
            "assumptions": [
                {"key": a.key, "interpretation": a.interpretation, "source": a.source}
                for a in self.assumptions
            ],
            "ambiguity": self.ambiguity.value,
            "bounded_alternatives": list(self.bounded_alternatives),
            "clarification_required": self.clarification_required,
        }

    @property
    def identity(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.canonical_payload())).hexdigest()


def normalize_objective(
    requested: str,
    *,
    assumptions: Iterable[ObjectiveAssumption] = (),
    ambiguity: ObjectiveAmbiguity = ObjectiveAmbiguity.NONE,
    bounded_alternatives: Iterable[str] = (),
    clarification_required: bool = False,
) -> NormalizedObjective:
    if not isinstance(requested, str) or not requested or requested.strip() != requested:
        raise ValueError("requested objective must be explicit")
    canonical = " ".join(unicodedata.normalize("NFKC", requested).split())
    if not canonical:
        raise ValueError("normalized objective cannot be empty")
    return NormalizedObjective(
        original=requested,
        canonical=canonical,
        assumptions=tuple(assumptions),
        ambiguity=ambiguity,
        bounded_alternatives=tuple(bounded_alternatives),
        clarification_required=clarification_required,
    )

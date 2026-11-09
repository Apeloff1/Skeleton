"""Determinism classification and replay comparison contracts.

VOL-296 defines explicit comparison semantics.  It does not execute work or
grant authority; callers supply observations and this module only classifies
and compares canonical values.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import math
from typing import Any, Mapping, Sequence

from skeleton.contracts.canonical import canonical_json_bytes


class DeterminismClass(str, Enum):
    EXACT = "exact"
    SEEDED = "seeded"
    TOLERANT = "tolerant"


@dataclass(frozen=True)
class VariancePolicy:
    absolute_tolerance: float = 0.0
    relative_tolerance: float = 0.0

    def __post_init__(self) -> None:
        for value in (self.absolute_tolerance, self.relative_tolerance):
            if not math.isfinite(value) or value < 0:
                raise ValueError("variance tolerances must be finite and non-negative")


@dataclass(frozen=True)
class DeterminismEnvelope:
    determinism_class: DeterminismClass
    seed: int | None = None
    variance: VariancePolicy = VariancePolicy()
    nondeterminism_sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        sources = tuple(self.nondeterminism_sources)
        if any(not isinstance(source, str) or not source.strip() for source in sources):
            raise ValueError("nondeterminism sources must be non-empty strings")
        if len(set(sources)) != len(sources):
            raise ValueError("nondeterminism sources must be unique")
        if self.determinism_class is DeterminismClass.EXACT:
            if self.seed is not None or self.variance != VariancePolicy() or sources:
                raise ValueError("exact determinism cannot declare seed, variance, or nondeterminism")
        elif self.determinism_class is DeterminismClass.SEEDED:
            if not isinstance(self.seed, int) or isinstance(self.seed, bool):
                raise ValueError("seeded determinism requires an integer seed")
            if self.variance != VariancePolicy():
                raise ValueError("seeded determinism must compare exactly")
        elif self.determinism_class is DeterminismClass.TOLERANT:
            if self.variance == VariancePolicy():
                raise ValueError("tolerant determinism requires an explicit tolerance")
            if not sources:
                raise ValueError("tolerant determinism must record nondeterminism sources")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "determinism_class": self.determinism_class.value,
            "seed": self.seed,
            "variance": {
                "absolute_tolerance": self.variance.absolute_tolerance,
                "relative_tolerance": self.variance.relative_tolerance,
            },
            "nondeterminism_sources": list(self.nondeterminism_sources),
        }

    @property
    def identity(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.canonical_payload())).hexdigest()


@dataclass(frozen=True)
class ReplayComparison:
    equivalent: bool
    envelope_id: str
    mismatch_paths: tuple[str, ...]


def compare_replay(expected: Any, actual: Any, envelope: DeterminismEnvelope) -> ReplayComparison:
    """Compare replay values under one explicit determinism envelope."""
    mismatches: list[str] = []
    _compare(expected, actual, envelope, "$", mismatches)
    return ReplayComparison(not mismatches, envelope.identity, tuple(mismatches))


def _compare(expected: Any, actual: Any, envelope: DeterminismEnvelope, path: str, out: list[str]) -> None:
    if isinstance(expected, bool) or isinstance(actual, bool):
        if type(expected) is not type(actual) or expected != actual:
            out.append(path)
        return
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if not math.isfinite(float(expected)) or not math.isfinite(float(actual)):
            raise ValueError("replay observations must contain only finite numbers")
        if envelope.determinism_class is DeterminismClass.TOLERANT:
            delta = abs(float(expected) - float(actual))
            scale = max(abs(float(expected)), abs(float(actual)))
            allowed = max(envelope.variance.absolute_tolerance, envelope.variance.relative_tolerance * scale)
            if delta > allowed:
                out.append(path)
        elif expected != actual:
            out.append(path)
        return
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        if any(not isinstance(key, str) for key in (*expected.keys(), *actual.keys())):
            raise ValueError("replay mapping keys must be strings")
        keys = sorted(set(expected) | set(actual))
        for key in keys:
            if key not in expected or key not in actual:
                out.append(f"{path}.{key}")
            else:
                _compare(expected[key], actual[key], envelope, f"{path}.{key}", out)
        return
    if isinstance(expected, Sequence) and not isinstance(expected, (str, bytes)) and isinstance(actual, Sequence) and not isinstance(actual, (str, bytes)):
        if len(expected) != len(actual):
            out.append(path)
            return
        for index, (left, right) in enumerate(zip(expected, actual)):
            _compare(left, right, envelope, f"{path}[{index}]", out)
        return
    if type(expected) is not type(actual) or expected != actual:
        out.append(path)

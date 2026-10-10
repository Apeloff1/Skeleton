"""Coverage accounting for deterministic factorial characterization campaigns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class CoverageObservation:
    observation_id: str
    factors: tuple[tuple[str, str], ...]
    replicate: int

    def __post_init__(self) -> None:
        if not self.observation_id:
            raise ReverseEngineeringError("coverage observation requires identity")
        if self.replicate < 1:
            raise ReverseEngineeringError("replicate must be positive")
        names = [name for name, _ in self.factors]
        if not names or any(not name or not value for name, value in self.factors):
            raise ReverseEngineeringError("coverage factors require non-empty names and values")
        if len(names) != len(set(names)):
            raise ReverseEngineeringError("coverage factor names must be unique")


@dataclass(frozen=True)
class ExperimentCoverageReport:
    expected_cell_count: int
    observed_cell_count: int
    missing_cell_count: int
    cell_coverage_ratio: float
    expected_replicates_per_cell: int
    fully_replicated_cell_count: int
    replicate_coverage_ratio: float
    missing_cells: tuple[tuple[tuple[str, str], ...], ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "expected_cell_count": self.expected_cell_count,
            "observed_cell_count": self.observed_cell_count,
            "missing_cell_count": self.missing_cell_count,
            "cell_coverage_ratio": self.cell_coverage_ratio,
            "expected_replicates_per_cell": self.expected_replicates_per_cell,
            "fully_replicated_cell_count": self.fully_replicated_cell_count,
            "replicate_coverage_ratio": self.replicate_coverage_ratio,
            "missing_cells": [[list(pair) for pair in cell] for cell in self.missing_cells],
            "digest": self.digest,
        }


def analyze_experiment_coverage(
    observations: Sequence[CoverageObservation],
    *,
    factor_levels: Mapping[str, Sequence[str]],
    expected_replicates_per_cell: int = 1,
) -> ExperimentCoverageReport:
    if not factor_levels:
        raise ReverseEngineeringError("coverage analysis requires factor levels")
    if expected_replicates_per_cell < 1:
        raise ReverseEngineeringError("expected_replicates_per_cell must be positive")
    ordered_names = tuple(sorted(factor_levels))
    levels: list[tuple[str, ...]] = []
    for name in ordered_names:
        values = tuple(factor_levels[name])
        if not values or len(values) != len(set(values)) or any(not value for value in values):
            raise ReverseEngineeringError(f"factor {name!r} must have unique non-empty levels")
        levels.append(values)

    expected: set[tuple[tuple[str, str], ...]] = {()}
    for name, values in zip(ordered_names, levels):
        expected = {
            cell + ((name, value),)
            for cell in expected
            for value in values
        }

    counts: dict[tuple[tuple[str, str], ...], set[int]] = {}
    for observation in observations:
        cell = tuple(sorted(observation.factors))
        if tuple(name for name, _ in cell) != ordered_names:
            raise ReverseEngineeringError("coverage observation factor set does not match design")
        if any(value not in factor_levels[name] for name, value in cell):
            raise ReverseEngineeringError("coverage observation uses unknown factor level")
        counts.setdefault(cell, set()).add(observation.replicate)

    observed_cells = set(counts) & expected
    missing = tuple(sorted(expected - observed_cells))
    fully_replicated = sum(
        len(counts.get(cell, set())) >= expected_replicates_per_cell
        for cell in expected
    )
    total_expected_replicates = len(expected) * expected_replicates_per_cell
    observed_replicates = sum(
        min(len(counts.get(cell, set())), expected_replicates_per_cell)
        for cell in expected
    )
    payload = {
        "factor_levels": {name: list(factor_levels[name]) for name in ordered_names},
        "expected_replicates_per_cell": expected_replicates_per_cell,
        "observations": [
            {
                "observation_id": item.observation_id,
                "factors": list(item.factors),
                "replicate": item.replicate,
            }
            for item in sorted(observations, key=lambda value: value.observation_id)
        ],
    }
    return ExperimentCoverageReport(
        expected_cell_count=len(expected),
        observed_cell_count=len(observed_cells),
        missing_cell_count=len(missing),
        cell_coverage_ratio=len(observed_cells) / len(expected),
        expected_replicates_per_cell=expected_replicates_per_cell,
        fully_replicated_cell_count=fully_replicated,
        replicate_coverage_ratio=(
            observed_replicates / total_expected_replicates
            if total_expected_replicates
            else 0.0
        ),
        missing_cells=missing,
        digest=stable_digest(payload),
    )

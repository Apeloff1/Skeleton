"""Deterministic controlled experiment matrix construction."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Mapping, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class ExperimentCell:
    cell_id: str
    factors: tuple[tuple[str, str], ...]
    replicate: int
    seed: int
    protocol_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "factors": [list(item) for item in self.factors],
            "replicate": self.replicate,
            "seed": self.seed,
            "protocol_digest": self.protocol_digest,
        }


def build_experiment_matrix(
    factors: Mapping[str, Sequence[str]],
    *,
    replicates: int = 3,
    seed: int = 0,
) -> tuple[ExperimentCell, ...]:
    if replicates < 1 or replicates > 100:
        raise ReverseEngineeringError("replicates must be within [1, 100]")
    if not factors:
        raise ReverseEngineeringError("experiment matrix requires factors")
    names = tuple(sorted(factors))
    levels: list[tuple[str, ...]] = []
    for name in names:
        values = tuple(str(value) for value in factors[name])
        if not values:
            raise ReverseEngineeringError(f"factor {name!r} requires at least one level")
        if len(set(values)) != len(values):
            raise ReverseEngineeringError(f"factor {name!r} contains duplicate levels")
        levels.append(values)

    cells: list[ExperimentCell] = []
    for combo in product(*levels):
        factor_tuple = tuple(zip(names, combo))
        base = stable_digest({"factors": factor_tuple, "seed": seed})
        for replicate in range(replicates):
            protocol = stable_digest(
                {"base": base, "replicate": replicate, "seed": seed}
            )
            cells.append(
                ExperimentCell(
                    cell_id=f"cell-{protocol[:16]}",
                    factors=factor_tuple,
                    replicate=replicate,
                    seed=seed,
                    protocol_digest=protocol,
                )
            )
    return tuple(sorted(cells, key=lambda cell: (cell.factors, cell.replicate)))

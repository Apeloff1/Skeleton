"""Snowball — conserved mass across the GameForge pipeline.

Each stage declares a mass contribution that sums to 1.0 when the run
is complete. Partial runs are honest about missing mass. The cockpit
may not mint mass; it may only observe and re-run a stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

STAGES: Tuple[str, ...] = (
    "ingest",
    "detect",
    "tensor",
    "lattice",
    "oracle",
    "forge",
    "jeeves",
    "sim",
    "emit",
    "seal",
)

WEIGHTS: Dict[str, float] = {
    "ingest": 0.05,
    "detect": 0.06,
    "tensor": 0.08,
    "lattice": 0.06,
    "oracle": 0.06,
    "forge": 0.18,
    "jeeves": 0.10,
    "sim": 0.16,
    "emit": 0.17,
    "seal": 0.08,
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


@dataclass
class Snowball:
    done: Dict[str, float] = field(default_factory=dict)
    log: List[str] = field(default_factory=list)

    def mark(self, stage: str) -> float:
        if stage not in WEIGHTS:
            raise KeyError(stage)
        self.done[stage] = WEIGHTS[stage]
        self.log.append(stage)
        return self.mass

    @property
    def mass(self) -> float:
        return round(sum(self.done.values()), 6)

    @property
    def complete(self) -> bool:
        return self.mass >= 1.0 - 1e-9

    def missing(self) -> List[str]:
        return [s for s in STAGES if s not in self.done]

    def to_dict(self) -> Dict[str, object]:
        return {
            "mass": self.mass,
            "complete": self.complete,
            "done": dict(self.done),
            "missing": self.missing(),
            "log": list(self.log),
        }

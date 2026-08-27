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
    "emit",
    "seal",
)

WEIGHTS: Dict[str, float] = {
    "ingest": 0.06,
    "detect": 0.08,
    "tensor": 0.10,
    "lattice": 0.08,
    "oracle": 0.08,
    "forge": 0.22,
    "jeeves": 0.14,
    "emit": 0.16,
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

"""Clipped-G Mass Control Engine — Milestone 1.
G grows only through MHC times S with clips. Mass per forge at most prior times 1.1.
No stamped G=10. observe_run mass_hint.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import math
import hashlib

class ClipMode(Enum):
    MHC_TIMES_S = "mhc_times_s"
    PRIOR_TIMES_1_1 = "prior_times_1_1"
    OBSERVE_HINT = "observe_hint"

@dataclass
class MassHint:
    g_delta: float
    mass_hint: float
    clip_applied: bool
    prior_mass: float
    new_mass: float
    mhc: float
    s: float

@dataclass
class ForgeMassRecord:
    forge_id: str
    prior: float
    computed: float
    clipped: float
    timestamp: float = field(default_factory=lambda: 0.0)

class ClippedMassEngine:
    """Byzantine mass governor. Labyrinthine clip lattice.
    Enforces G = clip(MHC * S, prior * 1.1). Emits observe_run hints.
    """
    def __init__(self, initial_g: float = 1.0, max_growth: float = 1.1) -> None:
        self._g = initial_g
        self._max_growth = max_growth
        self._records: List[ForgeMassRecord] = []
        self._hints: List[MassHint] = []
        self._invariant_lattice: Dict[str, Any] = {}

    def observe_run(self, forge_id: str, mhc: float, s: float, prior_mass: Optional[float] = None) -> MassHint:
        prior = prior_mass if prior_mass is not None else self._g
        raw = mhc * s
        clipped = min(raw, prior * self._max_growth)
        clip_applied = clipped < raw
        new_mass = clipped
        self._g = new_mass
        hint = MassHint(
            g_delta=new_mass - prior,
            mass_hint=new_mass,
            clip_applied=clip_applied,
            prior_mass=prior,
            new_mass=new_mass,
            mhc=mhc,
            s=s,
        )
        self._hints.append(hint)
        self._records.append(ForgeMassRecord(
            forge_id=forge_id,
            prior=prior,
            computed=raw,
            clipped=clipped,
        ))
        return hint

    def get_current_g(self) -> float:
        return self._g

    def export_chronicle(self) -> Dict[str, Any]:
        return {
            "current_g": self._g,
            "records": [r.__dict__ for r in self._records],
            "hints": [h.__dict__ for h in self._hints],
            "max_growth": self._max_growth,
        }

    def _compute_mhc(self, base: float, layers: int) -> float:
        return base * math.pow(1.05, layers)

    def _hash_mass(self, mass: float) -> str:
        return hashlib.sha256(f"{mass:.10f}".encode()).hexdigest()[:16]

"""
Clipped-G Observer for local AI workloads.
G grows only through MHC times S with clips. Mass per forge at most prior times 1.1.
Complete, no stubs.
"""
from dataclasses import dataclass
from typing import Dict

@dataclass
class ClippedGState:
    G: float = 10.0
    G_delta: float = 0.0
    mass_hint: float = 1.0
    clip: float = 1.1

class ClippedGObserver:
    def __init__(self):
        self.state = ClippedGState()

    def observe(self, metrics: Dict[str, float]) -> ClippedGState:
        delta = metrics.get("delta", 0.0)
        mass = metrics.get("mass", self.state.mass_hint)
        self.state.G_delta = delta
        self.state.mass_hint = min(self.state.mass_hint * self.state.clip, mass)
        self.state.G = min(self.state.G + delta, 10.0 * self.state.clip)
        return self.state

    def stamp(self) -> Dict:
        return {"G": self.state.G, "mass": self.state.mass_hint, "forbidden": self.state.G > 11.0}

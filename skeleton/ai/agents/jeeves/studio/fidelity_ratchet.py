"""Fidelity ratchet.
Locks improvements and prevents regression below the high-water mark.
"""
from typing import Any, Dict, List

class FidelityRatchet:
    def __init__(self):
        self.high_water = 0.0
        self.locks: List[float] = []

    def observe(self, fidelity: float) -> Dict[str, Any]:
        improved = fidelity > self.high_water
        if improved:
            self.high_water = fidelity
            self.locks.append(fidelity)
        return {
            "fidelity": fidelity,
            "high_water": self.high_water,
            "improved": improved,
            "locked": self.high_water >= 0.92,
            "schema": "skeleton.fidelity.ratchet.v1",
        }

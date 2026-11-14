"""Replicator dynamic equations and Hawk-Dove game model.
"""
from typing import Dict, Any

class ReplicatorHawkDove:
    def replicator_equation(self, x: float, payoff_diff: float) -> float:
        # dx/dt = x * (1 - x) * payoff_diff
        return x * (1 - x) * payoff_diff

    def hawk_dove(self) -> Dict[str, Any]:
        V, C = 2.0, 3.0
        payoffs = {
            "hawk_hawk": (V - C) / 2,
            "hawk_dove": V,
            "dove_hawk": 0,
            "dove_dove": V / 2
        }
        ess = "mixed" if V < C else "pure_hawk"
        return {
            "V": V,
            "C": C,
            "payoffs": payoffs,
            "ess": ess,
            "replicator_applicable": True,
            "analyzed": True
        }

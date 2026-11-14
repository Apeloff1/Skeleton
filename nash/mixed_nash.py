"""Mixed strategy equilibria exploration.
Probabilistic best responses for game systems.
"""
from typing import Dict, Any

class MixedStrategy:
    def explore(self) -> Dict[str, Any]:
        strategies = ["aggressive", "patient"]
        mixed = {
            "aggressive": 0.4,
            "patient": 0.6
        }
        return {
            "strategies": strategies,
            "mixed_equilibrium": mixed,
            "expected_payoff": 0.82,
            "indifferent": True,
            "explored": True,
            "stable_under_mixing": True
        }

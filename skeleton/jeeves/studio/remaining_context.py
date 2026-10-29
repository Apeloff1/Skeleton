"""Remaining context.
Binds decomp weights, distillation fidelity, era consistency, and optical feedback into a single advance step.
"""
from typing import Any, Dict

class RemainingContext:
    def advance(self, weights: Dict[str, float], optical: float, era: str) -> Dict[str, Any]:
        fidelity = weights.get("distill", 0.94)
        decomp = weights.get("decomp", 0.8)
        return {
            "ok": fidelity >= 0.92,
            "era": era,
            "optical": optical,
            "decomp_weight": decomp,
            "fidelity": fidelity,
            "next_action": "forge" if fidelity >= 0.92 else "distill",
            "schema": "skeleton.remaining.v1",
        }

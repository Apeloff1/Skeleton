"""distill_system_001. Distillation fidelity and card.
Concrete system for Jeeves game creation from decomp weights and distillation.
"""
from typing import Any, Dict

class DistillSystem001:
    CATEGORY = "distill"
    def process(self, weights: Dict[str, float], optical: float = 0.93) -> Dict[str, Any]:
        base = weights.get(self.CATEGORY, 0.5)
        return {
            "ok": True,
            "category": self.CATEGORY,
            "weight_applied": round(base * optical, 3),
            "output": {"modifier": round(base * 1.1, 2), "fidelity": 0.94},
            "schema": "skeleton.distill.v1",
        }

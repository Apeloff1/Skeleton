"""Weight fusion.
Fuses decomp, distill, and optical weights.
"""
from typing import Any, Dict

class WeightFusion:
    def fuse(self, weights: Dict[str, float]) -> Dict[str, Any]:
        if not isinstance(weights, dict) or not weights:
            return {"ok": False, "reason": "bad_weights", "schema": "skeleton.weight.fuse.v1"}
        try:
            fused = sum(float(v) for v in weights.values()) / len(weights)
        except (TypeError, ValueError):
            return {"ok": False, "reason": "bad_values", "schema": "skeleton.weight.fuse.v1"}
        return {"ok": True, "fused": round(fused, 3), "count": len(weights), "reason": "ok", "schema": "skeleton.weight.fuse.v1"}

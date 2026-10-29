"""Advanced local AI operational for end users.
Fail-closed on bad weights, multi-tier, weight fusion, optical floors, ratchet.
"""
from typing import Any, Dict, List

class LocalAIOperational:
    THRESH = {"draft": 0.85, "refine": 0.90, "final": 0.92}
    MODULES = ["level_gen", "behavior_gen", "asset_respray", "boss_seq", "narrative_branch", "proc_gen", "graphics"]

    def run(self, tier: str, weights: Dict[str, float], optical: float, ratchet: float) -> Dict[str, Any]:
        if not isinstance(weights, dict) or not weights:
            return {"ok": False, "reason": "bad_weights", "schema": "skeleton.local_ai.op.v4"}
        thresh = self.THRESH.get(tier, 0.92)
        fidelity = weights.get("distill", 0.0)
        try:
            fused = sum(float(v) for v in weights.values()) / max(1, len(weights))
        except (TypeError, ValueError):
            return {"ok": False, "reason": "bad_weight_values", "schema": "skeleton.local_ai.op.v4"}
        ok = fidelity >= thresh and optical >= 0.8 and fidelity >= ratchet and fused >= 0.7
        return {
            "tier": tier,
            "ok": ok,
            "fidelity": fidelity,
            "optical": optical,
            "ratchet": ratchet,
            "threshold": thresh,
            "fused": round(fused, 3),
            "weights": weights,
            "next": "advance" if ok else "retry",
            "modules": self.MODULES,
            "end_user_ready": ok and tier == "final",
            "reason": "ok" if ok else "gates_failed",
            "schema": "skeleton.local_ai.op.v4",
        }

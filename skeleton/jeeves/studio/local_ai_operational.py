"""Advanced local AI operational.
Multi-tier thresholds, weight fusion, optical floors, and ratchet lock.
"""
from typing import Any, Dict, List

class LocalAIOperational:
    THRESH = {"draft": 0.85, "refine": 0.90, "final": 0.92}

    def run(self, tier: str, weights: Dict[str, float], optical: float, ratchet: float) -> Dict[str, Any]:
        thresh = self.THRESH.get(tier, 0.92)
        fidelity = weights.get("distill", 0.94)
        fused = sum(weights.values()) / max(1, len(weights))
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
            "modules": ["level_gen", "behavior_gen", "asset_respray", "boss_seq", "narrative_branch", "proc_gen", "graphics"],
            "schema": "skeleton.local_ai.op.v2",
        }

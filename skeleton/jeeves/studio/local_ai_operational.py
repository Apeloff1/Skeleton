"""Advanced local AI operational for end users.
Multi-tier thresholds, weight fusion, optical floors, ratchet lock, and end-user status.
"""
from typing import Any, Dict, List

class LocalAIOperational:
    THRESH = {"draft": 0.85, "refine": 0.90, "final": 0.92}
    MODULES = ["level_gen", "behavior_gen", "asset_respray", "boss_seq", "narrative_branch", "proc_gen", "graphics"]

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
            "modules": self.MODULES,
            "end_user_ready": ok and tier == "final",
            "schema": "skeleton.local_ai.op.v3",
        }

    def status(self) -> Dict[str, Any]:
        return {
            "tiers": list(self.THRESH.keys()),
            "modules": self.MODULES,
            "ready": True,
            "schema": "skeleton.local_ai.status.v1",
        }

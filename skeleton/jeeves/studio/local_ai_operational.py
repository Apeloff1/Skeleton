"""Local AI operational.
Full draft/refine/final with decomp weights, optical, and ratchet.
"""
from typing import Any, Dict, List

class LocalAIOperational:
    def run(self, tier: str, weights: Dict[str, float], optical: float, ratchet: float) -> Dict[str, Any]:
        thresh = 0.85 if tier == "draft" else 0.90 if tier == "refine" else 0.92
        fidelity = weights.get("distill", 0.94)
        ok = fidelity >= thresh and optical >= 0.8 and fidelity >= ratchet
        return {
            "tier": tier,
            "ok": ok,
            "fidelity": fidelity,
            "optical": optical,
            "ratchet": ratchet,
            "threshold": thresh,
            "weights": weights,
            "next": "advance" if ok else "retry",
            "modules": ["level_gen", "behavior_gen", "asset_respray", "boss_seq", "narrative_branch"],
            "schema": "skeleton.local_ai.op.v1",
        }

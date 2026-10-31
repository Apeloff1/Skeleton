"""Advanced local AI loop.
Multi-tier thresholds, optical floors, and ratchet-aware advance.
"""
from typing import Any, Dict

class LocalAILoop:
    THRESH = {"draft": 0.85, "refine": 0.90, "final": 0.92}

    def step(self, tier: str, optical: float, fidelity: float, ratchet: float = 0.0) -> Dict[str, Any]:
        thresh = self.THRESH.get(tier, 0.92)
        ok = fidelity >= thresh and optical >= 0.8 and fidelity >= ratchet
        return {
            "tier": tier,
            "ok": ok,
            "threshold": thresh,
            "optical": optical,
            "fidelity": fidelity,
            "ratchet": ratchet,
            "next": "advance" if ok else "retry",
            "schema": "skeleton.local_ai.loop.v2",
        }

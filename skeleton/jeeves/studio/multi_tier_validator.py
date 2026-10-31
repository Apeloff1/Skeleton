"""Multi-tier validator.
Validates at draft, refine, and final tiers with escalating fidelity requirements.
"""
from typing import Any, Dict

class MultiTierValidator:
    THRESHOLDS = {"draft": 0.85, "refine": 0.90, "final": 0.92}

    def validate(self, tier: str, fidelity: float, optical: float) -> Dict[str, Any]:
        thresh = self.THRESHOLDS.get(tier, 0.92)
        ok = fidelity >= thresh and optical >= 0.8
        return {
            "ok": ok,
            "tier": tier,
            "threshold": thresh,
            "fidelity": fidelity,
            "optical": optical,
            "schema": "skeleton.validator.multi.v1",
        }

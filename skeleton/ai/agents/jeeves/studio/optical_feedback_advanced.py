"""Advanced optical feedback.
Drives difficulty, economy, boss aggression, and generation scale from optical diversity.
"""
from typing import Any, Dict

class OpticalFeedbackAdvanced:
    def compute(self, optical: float, rooms_cleared: int = 0) -> Dict[str, Any]:
        ease = max(0.0, min(1.0, optical))
        return {
            "difficulty": round(1.0 - ease * 0.4, 2),
            "enemy_mult": round(1.0 + (1.0 - ease) * 0.3, 2),
            "salvage_mult": round(1.0 + ease * 0.4, 2),
            "boss_aggression": round(0.5 + (1.0 - ease) * 0.4, 2),
            "gen_scale": round(1.0 + ease * 0.5, 2),
            "rooms_cleared": rooms_cleared,
            "schema": "skeleton.optical.advanced.v1",
        }

"""Optical feedback loop.
Scales difficulty, enemy, salvage, and boss from optical.
"""
from typing import Any, Dict

class OpticalFeedbackLoop:
    def tick(self, optical: float) -> Dict[str, Any]:
        if not isinstance(optical, (int, float)) or optical < 0 or optical > 1:
            return {"ok": False, "reason": "bad_optical", "schema": "skeleton.optical.loop.v1"}
        return {
            "ok": True,
            "optical": optical,
            "difficulty": round(0.5 + optical*0.5, 2),
            "enemy_mult": round(1.0 + optical*0.2, 2),
            "salvage_mult": round(1.0 + optical*0.3, 2),
            "boss_mult": round(1.0 + optical*0.4, 2),
            "reason": "ok",
            "schema": "skeleton.optical.loop.v1",
        }

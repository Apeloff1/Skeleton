"""Local AI loop.
Draft/refine/final with observe, generate, validate, and ratchet.
"""
from typing import Any, Dict

class LocalAILoop:
    def step(self, tier: str, optical: float, fidelity: float) -> Dict[str, Any]:
        ok = fidelity >= (0.85 if tier == "draft" else 0.90 if tier == "refine" else 0.92) and optical >= 0.8
        return {
            "tier": tier,
            "ok": ok,
            "optical": optical,
            "fidelity": fidelity,
            "next": "advance" if ok else "retry",
            "schema": "skeleton.local_ai.loop.v1",
        }

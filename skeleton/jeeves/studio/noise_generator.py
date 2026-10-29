"""Noise generator.
Value noise with optical scale.
"""
from typing import Any, Dict

class NoiseGenerator:
    def generate(self, size: int, optical: float) -> Dict[str, Any]:
        if not isinstance(size, int) or size < 1:
            return {"ok": False, "reason": "bad_size", "schema": "skeleton.noise.v1"}
        scale = round(0.5 + optical*0.5, 2)
        return {"ok": True, "size": size, "scale": scale, "optical": optical, "reason": "ok", "schema": "skeleton.noise.v1"}

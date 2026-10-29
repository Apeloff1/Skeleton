"""Advanced graphics.
Multi-pass LOD, optical frustum, mode projection, and era palette.
"""
from typing import Any, Dict, List

class AdvancedGraphics:
    def frame(self, mode: str, optical: float, entities: int, era: str, passes: int = 2) -> Dict[str, Any]:
        lod = 0 if optical > 0.95 else 1 if optical > 0.85 else 2
        culled = int(entities * (1.0 - optical * 0.3))
        return {
            "mode": mode,
            "lod": lod,
            "culled": culled,
            "visible": entities - culled,
            "optical": optical,
            "era": era,
            "passes": passes,
            "projection": "perspective" if mode in ["3d", "2.9d"] else "oblique",
            "palette": "#3a2a1a" if era == "ash" else "#2a2a3a",
            "schema": "skeleton.adv.graphics.v2",
        }

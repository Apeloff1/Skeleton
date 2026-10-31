"""Animation blending.
Optical-weighted pose interpolation.
"""
from typing import Any, Dict, List

class AnimationBlending:
    def blend(self, pose_a: Dict[str, float], pose_b: Dict[str, float], t: float, optical: float) -> Dict[str, float]:
        w = max(0.0, min(1.0, t * optical))
        keys = set(pose_a) | set(pose_b)
        return {k: pose_a.get(k, 0) * (1 - w) + pose_b.get(k, 0) * w for k in keys}

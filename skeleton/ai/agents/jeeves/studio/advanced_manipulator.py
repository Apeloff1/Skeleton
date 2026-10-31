"""Advanced manipulator.
Spatial transforms, optical-weighted blending, and chunk-aware edits.
"""
from typing import Any, Dict, List, Tuple
import math

class AdvancedManipulator:
    def transform(self, points: List[Tuple[float, float]], scale: float, rotation: float) -> List[Tuple[float, float]]:
        cos_r, sin_r = math.cos(rotation), math.sin(rotation)
        return [(x * scale * cos_r - y * scale * sin_r, x * scale * sin_r + y * scale * cos_r) for x, y in points]

    def blend(self, a: Dict[str, float], b: Dict[str, float], optical: float) -> Dict[str, float]:
        w = max(0.0, min(1.0, optical))
        return {k: a.get(k, 0) * (1 - w) + b.get(k, 0) * w for k in set(a) | set(b)}

    def chunk_edit(self, chunks: Dict[str, Dict], cid: str, key: str, value: float, optical: float) -> Dict[str, Any]:
        if cid not in chunks:
            chunks[cid] = {}
        prior = chunks[cid].get(key, value)
        blended = prior * (1 - optical) + value * optical
        chunks[cid][key] = blended
        return {"chunk": cid, "key": key, "value": blended, "optical": optical}

"""LOD system.
Level-of-detail selection from distance and optical.
"""
from typing import Any, Dict

class LODSystem:
    def select(self, distance: float, optical: float) -> int:
        base = 3 if optical > 0.9 else 2 if optical > 0.7 else 1
        if distance > 50:
            return max(0, base - 2)
        if distance > 20:
            return max(0, base - 1)
        return base

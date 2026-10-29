"""Procedural noise.
Value noise and optical-modulated heightmaps for terrain and textures.
"""
from typing import Any, Dict
import math

class ProceduralNoise:
    def value(self, x: float, y: float, seed: int = 8847291) -> float:
        n = math.sin(x * 12.9898 + y * 78.233 + seed) * 43758.5453
        return n - math.floor(n)

    def heightmap(self, width: int, height: int, optical: float) -> Dict[str, Any]:
        cells = [[self.value(x * 0.1, y * 0.1) * optical for x in range(width)] for y in range(height)]
        return {"width": width, "height": height, "optical": optical, "sample": cells[0][0] if cells else 0}

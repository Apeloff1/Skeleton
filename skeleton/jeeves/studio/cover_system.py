"""Cover system. Damage reduction behind cover."""
from typing import Any, Dict
class CoverSystem:
    def in_cover(self, pos: tuple, cover_zones: list) -> float:
        return 0.5 if any(abs(pos[0] - z[0]) < 2 for z in cover_zones) else 0.0

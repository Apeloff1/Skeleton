"""Cover system. Damage reduction behind cover."""
from typing import Any, Dict
class CoverSystem:
    def in_cover(self, pos: tuple, cover_zones: list) -> float:
        if not isinstance(pos, tuple) or not pos or isinstance(pos[0], bool) or not isinstance(pos[0], (int, float)):
            return 0.0
        if not isinstance(cover_zones, list):
            return 0.0
        origin = pos[0]
        for zone in cover_zones:
            point = None
            if isinstance(zone, tuple) and zone and isinstance(zone[0], (int, float)) and not isinstance(zone[0], bool):
                point = zone[0]
            elif isinstance(zone, dict):
                candidate = zone.get("x", zone.get(0))
                if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                    point = candidate
            if point is not None and abs(origin - point) < 2:
                return 0.5
        return 0.0

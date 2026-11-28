"""Cover system. Damage reduction behind cover."""
from math import isfinite


def _coordinate(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not isfinite(value):
        return None
    return value


class CoverSystem:
    def in_cover(self, pos: tuple, cover_zones: list) -> float:
        """Return half damage reduction within two horizontal units."""
        if not isinstance(pos, tuple) or not pos or not isinstance(cover_zones, list):
            return 0.0
        origin = _coordinate(pos[0])
        if origin is None:
            return 0.0
        for zone in cover_zones:
            if isinstance(zone, tuple) and zone:
                point = _coordinate(zone[0])
            elif isinstance(zone, dict):
                point = _coordinate(zone.get("x", zone.get(0)))
            else:
                continue
            if point is None:
                continue
            try:
                if abs(origin - point) < 2:
                    return 0.5
            except OverflowError:
                continue
        return 0.0

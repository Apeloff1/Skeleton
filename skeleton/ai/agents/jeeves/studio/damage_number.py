"""Damage number. Floating combat text values."""
from typing import Any, Dict
class DamageNumber:
    def spawn(self, value: int, pos: tuple, crit: bool = False) -> Dict[str, Any]:
        return {"value": value, "pos": pos, "crit": crit, "ttl": 0.8}

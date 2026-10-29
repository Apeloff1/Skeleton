"""Loot table.
Multi-tier loot with optical rarity.
"""
from typing import Any, Dict, List

class LootTable:
    def roll(self, optical: float, count: int = 3) -> Dict[str, Any]:
        if not isinstance(count, int) or count < 1:
            return {"ok": False, "reason": "bad_count", "schema": "skeleton.loot.table.v2"}
        items = [{"id": i, "rarity": "rare" if optical > 0.9 else "common", "value": int(10 + optical*20)} for i in range(count)]
        return {"ok": True, "items": items, "count": count, "optical": optical, "reason": "ok", "schema": "skeleton.loot.table.v2"}

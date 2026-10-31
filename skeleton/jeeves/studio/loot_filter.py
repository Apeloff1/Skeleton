"""Loot filter. Hides or prioritizes items by rarity and effect."""
from typing import Any, Dict, List
class LootFilter:
    def filter(self, items: List[Dict[str, Any]], min_rarity: str = "common") -> List[Dict[str, Any]]:
        order = ["common","uncommon","rare","epic","legendary"]
        min_i = order.index(min_rarity) if min_rarity in order else 0
        return [it for it in items if order.index(it.get("rarity","common")) >= min_i]

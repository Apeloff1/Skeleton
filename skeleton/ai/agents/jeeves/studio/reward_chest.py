"""Reward chest. Guaranteed loot after objectives."""
from typing import Any, Dict
class RewardChest:
    def open(self, difficulty: float) -> Dict[str, Any]:
        return {"value": int(15 * difficulty), "rarity": "rare"}

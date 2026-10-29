"""Combat resolver.
Resolves player vs enemy/boss exchanges with modifiers, weak points, and optical tags.
"""
from __future__ import annotations
from typing import Any, Dict

class CombatResolver:
    def resolve(self, player_dmg: float, enemy_health: float, weak_point: str = "", player_armor: float = 0.0, aggression: float = 0.7) -> Dict[str, Any]:
        effective = player_dmg * (1.5 if weak_point == "core" else 1.0)
        new_health = max(0.0, enemy_health - effective)
        counter = max(0.0, 8.0 * aggression - player_armor * 0.3)
        defeated = new_health <= 0.0
        return {
            "enemy_health": round(new_health, 1),
            "player_damage_taken": round(counter, 1),
            "defeated": defeated,
            "weak_hit": weak_point == "core",
            "optical_tag": "combat",
        }

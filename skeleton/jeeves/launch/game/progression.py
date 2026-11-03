"""Launch-ready game state and progression system.

Tracks player progress, inventory, quests, and unlocks.
Immediately usable by the app and by the AI conductor.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class PlayerState:
    health: int = 100
    max_health: int = 100
    level: int = 1
    xp: int = 0
    inventory: List[str] = field(default_factory=list)
    abilities: List[str] = field(default_factory=list)
    quests_completed: List[str] = field(default_factory=list)
    current_room: str = "r_000"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "health": self.health,
            "max_health": self.max_health,
            "level": self.level,
            "xp": self.xp,
            "inventory": list(self.inventory),
            "abilities": list(self.abilities),
            "quests_completed": list(self.quests_completed),
            "current_room": self.current_room,
        }


class ProgressionSystem:
    """Handles XP, leveling, ability unlocks, and quest completion."""

    XP_PER_LEVEL = 100

    def __init__(self) -> None:
        self.state = PlayerState()

    def add_xp(self, amount: int) -> Dict[str, Any]:
        if amount <= 0:
            return {"ok": False, "reason": "bad_amount"}
        self.state.xp += amount
        leveled = False
        while self.state.xp >= self.XP_PER_LEVEL:
            self.state.xp -= self.XP_PER_LEVEL
            self.state.level += 1
            self.state.max_health += 10
            self.state.health = self.state.max_health
            leveled = True
        return {"ok": True, "level": self.state.level, "leveled": leveled, "xp": self.state.xp}

    def unlock_ability(self, ability: str) -> Dict[str, Any]:
        if not ability:
            return {"ok": False, "reason": "empty"}
        if ability in self.state.abilities:
            return {"ok": False, "reason": "already_unlocked"}
        self.state.abilities.append(ability)
        return {"ok": True, "ability": ability, "total": len(self.state.abilities)}

    def complete_quest(self, quest_id: str, reward_xp: int = 50) -> Dict[str, Any]:
        if quest_id in self.state.quests_completed:
            return {"ok": False, "reason": "already_done"}
        self.state.quests_completed.append(quest_id)
        xp_result = self.add_xp(reward_xp)
        return {"ok": True, "quest": quest_id, "xp_result": xp_result}

    def add_item(self, item_id: str) -> Dict[str, Any]:
        if len(self.state.inventory) >= 12:
            return {"ok": False, "reason": "inventory_full"}
        self.state.inventory.append(item_id)
        return {"ok": True, "item": item_id, "count": len(self.state.inventory)}

    def snapshot(self) -> Dict[str, Any]:
        return self.state.to_dict()

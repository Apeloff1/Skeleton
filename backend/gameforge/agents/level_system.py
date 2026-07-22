from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


@dataclass
class AgentRoomProgress:
    room_id: str
    level: int = 1
    exp: float = 0.0
    unlocked_tiers: List[str] = field(default_factory=lambda: ["standard"])

    def exp_to_next(self) -> float:
        return 50.0 * (1.32 ** max(0, self.level - 1))

    def gain_exp(self, amount: float) -> Dict[str, Any]:
        self.exp += amount
        leveled = False
        while self.exp >= self.exp_to_next():
            self.exp -= self.exp_to_next()
            self.level += 1
            leveled = True
            if self.level >= 7 and "tier_2" not in self.unlocked_tiers:
                self.unlocked_tiers.append("tier_2")
            if self.level >= 16 and "tier_3" not in self.unlocked_tiers:
                self.unlocked_tiers.append("tier_3")
            if self.level >= 28 and "tier_4" not in self.unlocked_tiers:
                self.unlocked_tiers.append("tier_4")
        return {
            "room_id": self.room_id,
            "level": self.level,
            "exp": self.exp,
            "leveled": leveled,
            "unlocked_tiers": list(self.unlocked_tiers),
        }


class AgentLevelSystem:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.rooms: Dict[str, AgentRoomProgress] = {}

    def get_room(self, room_id: str) -> AgentRoomProgress:
        if room_id not in self.rooms:
            self.rooms[room_id] = AgentRoomProgress(room_id=room_id)
        return self.rooms[room_id]

    def grant_work_exp(self, room_id: str, amount: float = 12.0) -> Dict[str, Any]:
        return self.get_room(room_id).gain_exp(amount)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "rooms": {
                rid: {
                    "level": p.level,
                    "exp": p.exp,
                    "unlocked_tiers": p.unlocked_tiers,
                }
                for rid, p in self.rooms.items()
            },
        }

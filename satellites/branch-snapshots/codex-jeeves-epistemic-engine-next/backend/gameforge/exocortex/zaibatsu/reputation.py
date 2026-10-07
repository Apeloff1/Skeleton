from __future__ import annotations
"""
WoW-style reputation per room + EVE-style standings per team/member.
Jeeves uses these to bias agent selection, VOX priority, and unlock narrative.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import math


# WoW-like bands
REP_BANDS = [
    (-42000, "hated"),
    (-6000, "hostile"),
    (-3000, "unfriendly"),
    (0, "neutral"),
    (3000, "friendly"),
    (9000, "honored"),
    (21000, "revered"),
    (42000, "exalted"),
]


def rep_band(value: float) -> str:
    band = "hated"
    for threshold, name in REP_BANDS:
        if value >= threshold:
            band = name
    return band


@dataclass
class RoomReputation:
    room_id: str
    value: float = 0.0
    lifetime_gained: float = 0.0

    @property
    def band(self) -> str:
        return rep_band(self.value)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["band"] = self.band
        return d


@dataclass
class Standing:
    """EVE-style -10.0 .. +10.0"""
    entity_id: str
    entity_type: str  # team | member
    value: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class ReputationStandingsService:
    def __init__(self):
        self.rooms: Dict[str, RoomReputation] = {}
        self.standings: Dict[str, Standing] = {}

    def room(self, room_id: str) -> RoomReputation:
        if room_id not in self.rooms:
            self.rooms[room_id] = RoomReputation(room_id=room_id)
        return self.rooms[room_id]

    def gain_room_rep(self, room_id: str, amount: float, reason: str = "") -> Dict[str, Any]:
        r = self.room(room_id)
        r.value = max(-42000, min(42999, r.value + amount))
        if amount > 0:
            r.lifetime_gained += amount
        return {"room": r.to_dict(), "delta": amount, "reason": reason}

    def set_standing(self, entity_id: str, entity_type: str, value: float) -> Standing:
        value = max(-10.0, min(10.0, value))
        s = Standing(entity_id=entity_id, entity_type=entity_type, value=value)
        self.standings[f"{entity_type}:{entity_id}"] = s
        return s

    def adjust_standing(self, entity_id: str, entity_type: str, delta: float) -> Standing:
        key = f"{entity_type}:{entity_id}"
        cur = self.standings.get(key) or Standing(entity_id, entity_type, 0.0)
        return self.set_standing(entity_id, entity_type, cur.value + delta)

    def standing_of(self, entity_id: str, entity_type: str) -> float:
        s = self.standings.get(f"{entity_type}:{entity_id}")
        return s.value if s else 0.0

    def preferred_agents(self, room_id: str, agent_ids: List[str]) -> List[str]:
        """Higher member standing first; exalted rooms boost all."""
        room = self.room(room_id)
        boost = 0.5 if room.band in ("revered", "exalted") else 0.0

        def key(aid: str):
            return self.standing_of(aid, "member") + boost

        return sorted(agent_ids, key=key, reverse=True)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "rooms": {k: v.to_dict() for k, v in self.rooms.items()},
            "standings": {k: v.to_dict() for k, v in self.standings.items()},
        }

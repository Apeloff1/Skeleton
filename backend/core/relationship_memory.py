"""NPC relationship memory and interaction modifiers.

Mined from Newmove2's NPCMemory concepts and redesigned as deterministic,
framework-free domain state suitable for generated worlds and server authority.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


DEFAULT_IMPACTS: dict[str, int] = {
    "gift_loved": 25,
    "gift_liked": 15,
    "gift_neutral": 5,
    "gift_disliked": -10,
    "gift_hated": -25,
    "conversation_good": 5,
    "conversation_bad": -5,
    "quest_completed": 20,
    "quest_failed": -15,
    "helped_in_danger": 30,
    "attacked": -50,
    "theft_caught": -40,
    "compliment": 8,
    "insult": -12,
    "saved_life": 50,
}


@dataclass(frozen=True, slots=True)
class Interaction:
    kind: str
    impact: int
    topic: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RelationshipModifiers:
    tier: str
    greeting: str
    secrets: bool
    price_multiplier: float
    quest_band: str


class RelationshipMemory:
    def __init__(self, npc_id: str, *, max_history: int = 50) -> None:
        if not npc_id.strip():
            raise ValueError("npc_id cannot be blank")
        if max_history < 1:
            raise ValueError("max_history must be positive")
        self.npc_id = npc_id
        self.max_history = max_history
        self.relationship = 0
        self.trust = 0
        self.fear = 0
        self._history: deque[Interaction] = deque(maxlen=max_history)
        self.impressions: dict[str, int] = {}
        self.completed_quests: set[str] = set()
        self.failed_quests: set[str] = set()

    @property
    def history(self) -> tuple[Interaction, ...]:
        return tuple(self._history)

    def record(
        self,
        kind: str,
        *,
        impact: int | None = None,
        topic: str | None = None,
        trust_delta: int = 0,
        fear_delta: int = 0,
        detail: dict[str, Any] | None = None,
    ) -> Interaction:
        if not kind.strip():
            raise ValueError("interaction kind cannot be blank")
        resolved = DEFAULT_IMPACTS.get(kind, 0) if impact is None else int(impact)
        event = Interaction(kind, resolved, topic, dict(detail or {}))
        self._history.append(event)
        self.relationship = max(-100, min(100, self.relationship + resolved))
        self.trust = max(-100, min(100, self.trust + int(trust_delta)))
        self.fear = max(0, min(100, self.fear + int(fear_delta)))
        self.impressions[kind] = self.impressions.get(kind, 0) + 1
        return event

    def mark_quest(self, quest_id: str, *, completed: bool) -> None:
        if not quest_id.strip():
            raise ValueError("quest_id cannot be blank")
        if completed:
            self.failed_quests.discard(quest_id)
            if quest_id not in self.completed_quests:
                self.completed_quests.add(quest_id)
                self.record("quest_completed", detail={"quest_id": quest_id}, trust_delta=5)
        else:
            self.completed_quests.discard(quest_id)
            if quest_id not in self.failed_quests:
                self.failed_quests.add(quest_id)
                self.record("quest_failed", detail={"quest_id": quest_id}, trust_delta=-5)

    def tier(self) -> str:
        value = self.relationship
        if value >= 80:
            return "best_friend"
        if value >= 50:
            return "close_friend"
        if value >= 20:
            return "friend"
        if value >= 0:
            return "acquaintance"
        if value >= -30:
            return "neutral"
        if value >= -60:
            return "disliked"
        return "enemy"

    def modifiers(self) -> RelationshipModifiers:
        table = {
            "best_friend": ("enthusiastic", True, 0.70, "special"),
            "close_friend": ("warm", True, 0.80, "advanced"),
            "friend": ("friendly", False, 0.90, "standard"),
            "acquaintance": ("polite", False, 1.00, "basic"),
            "neutral": ("neutral", False, 1.00, "none"),
            "disliked": ("cold", False, 1.15, "none"),
            "enemy": ("hostile", False, 1.50, "none"),
        }
        tier = self.tier()
        greeting, secrets, price, quests = table[tier]
        return RelationshipModifiers(tier, greeting, secrets, price, quests)

    def remembers_topic(self, topic: str) -> bool:
        return any(event.topic == topic for event in self._history)

    def recent_mood(self, *, count: int = 5) -> str:
        if count < 1:
            raise ValueError("count must be positive")
        score = sum(event.impact for event in tuple(self._history)[-count:])
        if score > 10:
            return "happy"
        if score > 5:
            return "content"
        if score < -10:
            return "annoyed"
        if score < -5:
            return "sad"
        return "neutral"

    def snapshot(self) -> dict[str, Any]:
        return {
            "npc_id": self.npc_id,
            "relationship": self.relationship,
            "trust": self.trust,
            "fear": self.fear,
            "tier": self.tier(),
            "impressions": dict(self.impressions),
            "completed_quests": sorted(self.completed_quests),
            "failed_quests": sorted(self.failed_quests),
            "history": [
                {
                    "kind": event.kind,
                    "impact": event.impact,
                    "topic": event.topic,
                    "detail": dict(event.detail),
                }
                for event in self._history
            ],
        }

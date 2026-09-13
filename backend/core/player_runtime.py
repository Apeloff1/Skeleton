"""Unified player runtime for the Play pillar.

Composes progression, quests and faction reputation behind one event-ingestion
surface so mined game systems can evolve together without coupling routes to
individual legacy modules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.progression import Medal, ProgressionState
from core.quest_graph import QuestCompletion, QuestGraph
from core.reputation import ReputationState


@dataclass(slots=True)
class PlayerRuntime:
    progression: ProgressionState
    quests: QuestGraph
    reputation: ReputationState
    inventory: dict[str, int] = field(default_factory=dict)
    xp: int = 0
    gold: int = 0

    def apply_rewards(self, rewards: dict[str, Any]) -> None:
        self.xp += int(rewards.get("xp", 0) or 0)
        self.gold += int(rewards.get("gold", 0) or 0)
        item = rewards.get("item")
        if item:
            self.inventory[str(item)] = self.inventory.get(str(item), 0) + 1
        items = rewards.get("items") or {}
        if isinstance(items, dict):
            for key, count in items.items():
                self.inventory[str(key)] = self.inventory.get(str(key), 0) + int(count)
        rep = rewards.get("reputation") or {}
        if isinstance(rep, dict):
            for faction_id, delta in rep.items():
                if faction_id in self.reputation.factions:
                    self.reputation.adjust(str(faction_id), int(delta))

    def ingest_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        amount: int = 1,
    ) -> tuple[QuestCompletion, ...]:
        completions = self.quests.ingest(event_type, payload, amount=amount)
        for completion in completions:
            self.apply_rewards(completion.rewards)
        return completions

    def record_finish(
        self,
        stage_id: str,
        *,
        score: float,
        medal: Medal,
        ghost: list[dict[str, Any]] | None = None,
        distance: float = 0.0,
        unlocks: dict[str, tuple[str, ...]] | None = None,
    ) -> dict[str, Any]:
        result = self.progression.record_finish(
            stage_id,
            score=score,
            medal=medal,
            ghost=ghost,
            distance=distance,
            unlocks=unlocks,
        )
        completions = self.ingest_event(
            "complete_stage",
            {"stage_id": stage_id, "medal": int(medal)},
        )
        return {
            "progression": result,
            "quest_completions": completions,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "xp": self.xp,
            "gold": self.gold,
            "inventory": dict(self.inventory),
            "progression": self.progression.snapshot(),
            "completed_quests": self.quests.completed_ids(),
            "reputation": dict(self.reputation.values),
        }

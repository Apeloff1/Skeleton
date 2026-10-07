"""Storage-neutral quest graph mined from Openworld4's large quest catalogue.

The original system mixed hundreds of quest records with HTTP/Mongo concerns.
This runtime keeps the reusable mechanics: typed objectives, prerequisites,
progress events, completion, rewards, and unlock propagation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Objective:
    type: str
    target: int = 1
    filters: tuple[tuple[str, Any], ...] = ()

    def matches(self, event_type: str, payload: dict[str, Any]) -> bool:
        if event_type != self.type:
            return False
        return all(payload.get(key) == value for key, value in self.filters)


@dataclass(frozen=True, slots=True)
class QuestDefinition:
    id: str
    title: str
    objectives: tuple[Objective, ...]
    prerequisite: str | None = None
    rewards: tuple[tuple[str, Any], ...] = ()
    category: str = "side"


@dataclass(slots=True)
class QuestProgress:
    quest_id: str
    counts: list[int]
    completed: bool = False


@dataclass(frozen=True, slots=True)
class QuestCompletion:
    quest_id: str
    rewards: dict[str, Any]
    newly_available: tuple[str, ...]


class QuestGraph:
    def __init__(self, definitions: tuple[QuestDefinition, ...]) -> None:
        ids = [q.id for q in definitions]
        if len(ids) != len(set(ids)):
            raise ValueError("quest ids must be unique")
        self._defs = {q.id: q for q in definitions}
        for quest in definitions:
            if quest.prerequisite and quest.prerequisite not in self._defs:
                raise ValueError(f"unknown prerequisite {quest.prerequisite!r}")
        self._completed: set[str] = set()
        self._active: dict[str, QuestProgress] = {}

    def available(self) -> tuple[QuestDefinition, ...]:
        rows = []
        for quest in self._defs.values():
            if quest.id in self._completed or quest.id in self._active:
                continue
            if quest.prerequisite is None or quest.prerequisite in self._completed:
                rows.append(quest)
        return tuple(rows)

    def activate(self, quest_id: str) -> QuestProgress:
        quest = self._defs.get(quest_id)
        if quest is None:
            raise KeyError(quest_id)
        if quest_id in self._completed:
            raise ValueError("quest already completed")
        if quest.prerequisite and quest.prerequisite not in self._completed:
            raise ValueError("quest prerequisite not completed")
        progress = self._active.get(quest_id)
        if progress is None:
            progress = QuestProgress(quest_id, [0] * len(quest.objectives))
            self._active[quest_id] = progress
        return progress

    def ingest(self, event_type: str, payload: dict[str, Any] | None = None, *, amount: int = 1) -> tuple[QuestCompletion, ...]:
        if amount <= 0:
            raise ValueError("amount must be positive")
        payload = payload or {}
        completions: list[QuestCompletion] = []
        for quest_id, progress in tuple(self._active.items()):
            quest = self._defs[quest_id]
            if progress.completed:
                continue
            for index, objective in enumerate(quest.objectives):
                if progress.counts[index] >= objective.target:
                    continue
                if objective.matches(event_type, payload):
                    progress.counts[index] = min(objective.target, progress.counts[index] + amount)
            if all(count >= objective.target for count, objective in zip(progress.counts, quest.objectives)):
                progress.completed = True
                self._completed.add(quest_id)
                self._active.pop(quest_id, None)
                unlocked = tuple(sorted(q.id for q in self.available() if q.prerequisite == quest_id))
                completions.append(QuestCompletion(quest_id, dict(quest.rewards), unlocked))
        return tuple(completions)

    def progress(self, quest_id: str) -> QuestProgress | None:
        return self._active.get(quest_id)

    def completed_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._completed))

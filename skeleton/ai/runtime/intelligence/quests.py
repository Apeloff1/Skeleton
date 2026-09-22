"""Quest planning primitives distilled from Newmove's large quest catalog."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class QuestObjective:
    kind: str
    target: str | None = None
    count: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QuestTemplate:
    id: str
    quest_type: str
    objectives: tuple[QuestObjective, ...]
    rewards: Mapping[str, Any] = field(default_factory=dict)
    prerequisites: tuple[str, ...] = ()
    tags: frozenset[str] = frozenset()


@dataclass(frozen=True)
class QuestProgress:
    completed: frozenset[str] = frozenset()
    facts: Mapping[str, Any] = field(default_factory=dict)
    objective_counts: Mapping[str, int] = field(default_factory=dict)

    def prerequisite_ready(self, quest: QuestTemplate) -> bool:
        return all(req in self.completed for req in quest.prerequisites)

    def objective_complete(self, objective: QuestObjective) -> bool:
        key = objective.target or objective.kind
        return self.objective_counts.get(key, 0) >= objective.count

    def ready_to_turn_in(self, quest: QuestTemplate) -> bool:
        return self.prerequisite_ready(quest) and all(self.objective_complete(o) for o in quest.objectives)


def rank_quest_candidates(
    quests: tuple[QuestTemplate, ...],
    progress: QuestProgress,
    *,
    preferred_tags: frozenset[str] = frozenset(),
    max_results: int = 5,
) -> tuple[QuestTemplate, ...]:
    """Rank available quests for an adaptive school/game agent."""
    candidates = [q for q in quests if progress.prerequisite_ready(q) and q.id not in progress.completed]
    scored = []
    for quest in candidates:
        score = len(quest.tags & preferred_tags) * 10
        score += 3 if quest.quest_type in {"side", "relationship"} else 0
        score += 2 if quest.quest_type == "daily" else 0
        scored.append((score, quest.id, quest))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return tuple(item[2] for item in scored[:max_results])

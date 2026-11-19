"""Deterministic training curriculum for Mirror Room.

Only training-split evidence participates. Validation and sealed holdout data
never enter this scheduler.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

from .contracts import (
    HardExample,
    MirrorRoomError,
    MirrorScenario,
    ScenarioSplit,
    _digest,
    _finite,
)


@dataclass(frozen=True, slots=True)
class CurriculumPolicy:
    hard_example_boost: float = 4.0
    tag_rarity_boost: float = 0.25
    base_weight_boost: float = 1.0
    max_hard_difficulty: float = 8.0
    interleave_primary_tags: bool = True

    def __post_init__(self) -> None:
        for field in (
            "hard_example_boost",
            "tag_rarity_boost",
            "base_weight_boost",
            "max_hard_difficulty",
        ):
            object.__setattr__(
                self,
                field,
                _finite(field, getattr(self, field), minimum=0.0),
            )
        if not isinstance(self.interleave_primary_tags, bool):
            raise MirrorRoomError("interleave_primary_tags must be boolean")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "hard_example_boost": self.hard_example_boost,
                "tag_rarity_boost": self.tag_rarity_boost,
                "base_weight_boost": self.base_weight_boost,
                "max_hard_difficulty": self.max_hard_difficulty,
                "interleave_primary_tags": self.interleave_primary_tags,
            }
        )


@dataclass(frozen=True, slots=True)
class CurriculumItem:
    scenario_id: str
    scenario_digest: str
    priority: float
    hard_difficulty: float
    rarity_score: float
    primary_tag: str

    @property
    def digest(self) -> str:
        return _digest(
            {
                "scenario_id": self.scenario_id,
                "scenario_digest": self.scenario_digest,
                "priority": self.priority,
                "hard_difficulty": self.hard_difficulty,
                "rarity_score": self.rarity_score,
                "primary_tag": self.primary_tag,
            }
        )


@dataclass(frozen=True, slots=True)
class CurriculumPlan:
    policy_digest: str
    scenarios: tuple[MirrorScenario, ...]
    items: tuple[CurriculumItem, ...]

    def __post_init__(self) -> None:
        if not self.scenarios:
            raise MirrorRoomError("curriculum requires training scenarios")
        if len(self.scenarios) != len(self.items):
            raise MirrorRoomError("curriculum scenario/item cardinality mismatch")
        if any(item.split is not ScenarioSplit.TRAIN for item in self.scenarios):
            raise MirrorRoomError("curriculum may contain only training scenarios")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "policy_digest": self.policy_digest,
                "scenario_digests": [item.digest for item in self.scenarios],
                "items": [item.digest for item in self.items],
            }
        )


def _primary_tag(scenario: MirrorScenario) -> str:
    return scenario.tags[0] if scenario.tags else "__untagged__"


def _interleave(
    ordered: Sequence[tuple[MirrorScenario, CurriculumItem]],
) -> list[tuple[MirrorScenario, CurriculumItem]]:
    remaining = list(ordered)
    result: list[tuple[MirrorScenario, CurriculumItem]] = []
    previous_tag: str | None = None
    while remaining:
        index = 0
        if previous_tag is not None:
            for candidate_index, (_, item) in enumerate(remaining):
                if item.primary_tag != previous_tag:
                    index = candidate_index
                    break
        chosen = remaining.pop(index)
        result.append(chosen)
        previous_tag = chosen[1].primary_tag
    return result


def build_curriculum(
    scenarios: Iterable[MirrorScenario],
    hard_examples: Iterable[HardExample] = (),
    *,
    policy: CurriculumPolicy | None = None,
) -> CurriculumPlan:
    actual = policy or CurriculumPolicy()
    train = tuple(scenarios)
    if not train:
        raise MirrorRoomError("curriculum requires training scenarios")
    if any(
        not isinstance(item, MirrorScenario) or item.split is not ScenarioSplit.TRAIN
        for item in train
    ):
        raise MirrorRoomError("curriculum accepts only Mirror Room training scenarios")

    ids = [item.scenario_id for item in train]
    if len(ids) != len(set(ids)):
        raise MirrorRoomError("curriculum scenario IDs must be unique")

    hard = tuple(hard_examples)
    if any(not isinstance(item, HardExample) for item in hard):
        raise MirrorRoomError("curriculum hard examples must contain HardExample")
    hard_by_id = {item.scenario_id: item for item in hard}
    if set(hard_by_id) - set(ids):
        raise MirrorRoomError("hard example does not belong to training curriculum")

    tag_counts: Counter[str] = Counter(_primary_tag(item) for item in train)
    rows: list[tuple[MirrorScenario, CurriculumItem]] = []
    for scenario in train:
        hard_item = hard_by_id.get(scenario.scenario_id)
        hard_difficulty = (
            0.0
            if hard_item is None
            else min(actual.max_hard_difficulty, hard_item.difficulty)
        )
        tag = _primary_tag(scenario)
        rarity = 1.0 / tag_counts[tag]
        priority = (
            scenario.weight * actual.base_weight_boost
            + hard_difficulty * actual.hard_example_boost
            + rarity * actual.tag_rarity_boost
        )
        rows.append(
            (
                scenario,
                CurriculumItem(
                    scenario_id=scenario.scenario_id,
                    scenario_digest=scenario.digest,
                    priority=priority,
                    hard_difficulty=hard_difficulty,
                    rarity_score=rarity,
                    primary_tag=tag,
                ),
            )
        )

    rows.sort(key=lambda row: (-row[1].priority, row[0].scenario_id))
    if actual.interleave_primary_tags:
        rows = _interleave(rows)
    return CurriculumPlan(
        policy_digest=actual.digest,
        scenarios=tuple(row[0] for row in rows),
        items=tuple(row[1] for row in rows),
    )


__all__ = [
    "CurriculumItem",
    "CurriculumPlan",
    "CurriculumPolicy",
    "build_curriculum",
]

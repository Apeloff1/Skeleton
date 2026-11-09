"""Generic prerequisite skill graph mined from Newmove2 progression data.

Supports level caps, currency costs, category unlock levels, prerequisite levels,
and deterministic aggregation of numeric/boolean effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class SkillRequirement:
    skill_id: str
    level: int


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    id: str
    category: str
    max_level: int
    costs: tuple[int, ...]
    effects: Mapping[str, float | bool]
    requires: tuple[SkillRequirement, ...] = ()
    unlock_level: int = 1

    def __post_init__(self) -> None:
        if not self.id or not self.category:
            raise ValueError("skill id and category are required")
        if self.max_level <= 0 or len(self.costs) != self.max_level:
            raise ValueError("cost schedule must match max_level")
        if any(cost < 0 for cost in self.costs):
            raise ValueError("skill costs cannot be negative")
        if self.unlock_level <= 0:
            raise ValueError("unlock_level must be positive")


@dataclass(slots=True)
class SkillProfile:
    points: int = 0
    levels: dict[str, int] = field(default_factory=dict)


class SkillGraph:
    def __init__(self, definitions: list[SkillDefinition]) -> None:
        self._skills = {skill.id: skill for skill in definitions}
        if len(self._skills) != len(definitions):
            raise ValueError("duplicate skill id")
        for skill in definitions:
            for requirement in skill.requires:
                target = self._skills.get(requirement.skill_id)
                if target is None:
                    raise ValueError(f"unknown skill prerequisite: {requirement.skill_id}")
                if requirement.level <= 0 or requirement.level > target.max_level:
                    raise ValueError("invalid prerequisite level")
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(skill_id: str) -> None:
            if skill_id in visiting:
                raise ValueError("skill graph contains a cycle")
            if skill_id in visited:
                return
            visiting.add(skill_id)
            for requirement in self._skills[skill_id].requires:
                visit(requirement.skill_id)
            visiting.remove(skill_id)
            visited.add(skill_id)

        for skill_id in self._skills:
            visit(skill_id)

    def definition(self, skill_id: str) -> SkillDefinition:
        try:
            return self._skills[skill_id]
        except KeyError as exc:
            raise KeyError(f"unknown skill: {skill_id}") from exc

    def can_purchase(self, profile: SkillProfile, skill_id: str, *, player_level: int) -> bool:
        skill = self.definition(skill_id)
        current = profile.levels.get(skill_id, 0)
        if current >= skill.max_level or player_level < skill.unlock_level:
            return False
        if profile.points < skill.costs[current]:
            return False
        return all(profile.levels.get(req.skill_id, 0) >= req.level for req in skill.requires)

    def purchase(self, profile: SkillProfile, skill_id: str, *, player_level: int) -> int:
        if not self.can_purchase(profile, skill_id, player_level=player_level):
            raise ValueError("skill purchase requirements not met")
        skill = self.definition(skill_id)
        current = profile.levels.get(skill_id, 0)
        profile.points -= skill.costs[current]
        profile.levels[skill_id] = current + 1
        return current + 1

    def effects(self, profile: SkillProfile) -> dict[str, float | bool]:
        result: dict[str, float | bool] = {}
        for skill_id, level in profile.levels.items():
            if level <= 0:
                continue
            skill = self.definition(skill_id)
            capped = min(level, skill.max_level)
            for key, value in skill.effects.items():
                if isinstance(value, bool):
                    result[key] = bool(result.get(key, False)) or value
                else:
                    result[key] = float(result.get(key, 0.0)) + float(value) * capped
        return result

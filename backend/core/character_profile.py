"""Portable character profile and background progression from Newmove2.

Keeps background-derived bonuses, skill growth and derived checks separate from
presentation and persistence. This gives generated RPG playables a compact,
engine-neutral character layer that composes with reputation and skill graphs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class CharacterBackground:
    id: str
    stat_bonuses: Mapping[str, int]
    starting_items: tuple[str, ...] = ()
    starting_currency: int = 0

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("background id is required")
        if self.starting_currency < 0:
            raise ValueError("starting currency cannot be negative")


@dataclass(slots=True)
class CharacterProfile:
    name: str
    stats: dict[str, int] = field(default_factory=lambda: {
        "strength": 5,
        "agility": 5,
        "wisdom": 5,
        "charisma": 5,
        "luck": 5,
        "endurance": 5,
    })
    skills: dict[str, int] = field(default_factory=dict)
    inventory: dict[str, int] = field(default_factory=dict)
    currency: int = 0
    level: int = 1
    experience: int = 0
    background_id: str | None = None

    def apply_background(self, background: CharacterBackground) -> None:
        if self.background_id is not None:
            raise ValueError("background already applied")
        for stat, bonus in background.stat_bonuses.items():
            self.stats[stat] = self.stats.get(stat, 0) + int(bonus)
        for item in background.starting_items:
            self.inventory[item] = self.inventory.get(item, 0) + 1
        self.currency += background.starting_currency
        self.background_id = background.id

    @staticmethod
    def xp_for_level(level: int) -> int:
        if level <= 0:
            raise ValueError("level must be positive")
        return 100 * level * level

    def grant_experience(self, amount: int) -> int:
        if amount < 0:
            raise ValueError("experience grant cannot be negative")
        self.experience += amount
        gained = 0
        while self.experience >= self.xp_for_level(self.level):
            self.experience -= self.xp_for_level(self.level)
            self.level += 1
            gained += 1
        return gained

    def train(self, skill_id: str, amount: int = 1, *, max_level: int = 10) -> int:
        if not skill_id or amount <= 0 or max_level <= 0:
            raise ValueError("invalid skill training request")
        current = self.skills.get(skill_id, 0)
        self.skills[skill_id] = min(max_level, current + amount)
        return self.skills[skill_id]

    def check(self, stat: str, skill: str | None = None) -> int:
        value = self.stats.get(stat, 0)
        if skill:
            value += self.skills.get(skill, 0)
        return value

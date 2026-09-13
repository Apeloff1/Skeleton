"""Crew roster and aggregate vessel bonuses mined from Openworld4 ship systems."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CrewRole:
    id: str
    max_per_ship: int
    salary: int
    bonuses: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or self.max_per_ship <= 0 or self.salary < 0:
            raise ValueError("invalid crew role")


@dataclass(slots=True)
class CrewMember:
    id: str
    role: CrewRole
    level: int = 1
    morale: float = 100.0
    health: float = 100.0

    @property
    def effectiveness(self) -> float:
        level_factor = 1 + max(0, self.level - 1) * 0.05
        condition = max(0.0, min(1.0, (self.morale / 100) * (self.health / 100)))
        return level_factor * condition


class CrewRoster:
    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self.members: dict[str, CrewMember] = {}

    def enlist(self, member: CrewMember) -> None:
        if not member.id or member.id in self.members:
            raise ValueError("crew id must be unique and non-empty")
        if len(self.members) >= self.capacity:
            raise RuntimeError("crew capacity exceeded")
        same_role = sum(1 for item in self.members.values() if item.role.id == member.role.id)
        if same_role >= member.role.max_per_ship:
            raise RuntimeError(f"role limit reached: {member.role.id}")
        self.members[member.id] = member

    def dismiss(self, member_id: str) -> CrewMember | None:
        return self.members.pop(member_id, None)

    def payroll(self) -> int:
        return sum(member.role.salary for member in self.members.values())

    def aggregate_bonuses(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for member in self.members.values():
            for key, value in member.role.bonuses.items():
                totals[key] = totals.get(key, 0.0) + float(value) * member.effectiveness
        return totals

    def tick_condition(self, *, morale_delta: float = 0.0, health_delta: float = 0.0) -> None:
        for member in self.members.values():
            member.morale = min(100.0, max(0.0, member.morale + morale_delta))
            member.health = min(100.0, max(0.0, member.health + health_delta))

    def snapshot(self) -> dict[str, object]:
        return {
            "capacity": self.capacity,
            "count": len(self.members),
            "payroll": self.payroll(),
            "bonuses": self.aggregate_bonuses(),
            "members": [
                {
                    "id": member.id,
                    "role": member.role.id,
                    "level": member.level,
                    "morale": member.morale,
                    "health": member.health,
                    "effectiveness": member.effectiveness,
                }
                for member in self.members.values()
            ],
        }

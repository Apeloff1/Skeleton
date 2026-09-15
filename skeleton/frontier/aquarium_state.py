"""Immutable aquarium state and transition result types."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping

from skeleton.frontier.aquarium_models import AquariumPosition, DisplayFish, aware, count, counts, text


@dataclass(frozen=True, slots=True)
class PlacedDecoration:
    id: str
    decoration_id: str
    name: str
    position: AquariumPosition
    placed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", text(self.id, "placed decoration id"))
        object.__setattr__(self, "decoration_id", text(self.decoration_id, "decoration id"))
        object.__setattr__(self, "name", text(self.name, "placed decoration name"))
        if not isinstance(self.position, AquariumPosition):
            raise TypeError("decoration position must be AquariumPosition")
        object.__setattr__(self, "placed_at", aware(self.placed_at, "placed_at"))


@dataclass(frozen=True, slots=True)
class AquariumTankState:
    tank_id: str
    fish: tuple[DisplayFish, ...] = ()
    decorations: tuple[PlacedDecoration, ...] = ()
    theme: str = "ocean"

    def __post_init__(self) -> None:
        object.__setattr__(self, "tank_id", text(self.tank_id, "state tank id"))
        object.__setattr__(self, "theme", text(self.theme, "tank theme"))
        if not all(isinstance(item, DisplayFish) for item in self.fish):
            raise TypeError("tank fish must be DisplayFish")
        if not all(isinstance(item, PlacedDecoration) for item in self.decorations):
            raise TypeError("tank decorations must be PlacedDecoration")
        fish_ids = [item.id for item in self.fish]
        decoration_ids = [item.id for item in self.decorations]
        if len(fish_ids) != len(set(fish_ids)):
            raise ValueError("duplicate fish identity in tank")
        if len(decoration_ids) != len(set(decoration_ids)):
            raise ValueError("duplicate decoration identity in tank")


@dataclass(frozen=True, slots=True)
class AquariumState:
    tanks: Mapping[str, AquariumTankState]
    owned_tanks: frozenset[str]
    owned_decorations: Mapping[str, int] = field(default_factory=dict)
    total_fish_displayed: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.tanks, Mapping):
            raise TypeError("tanks must be a mapping")
        tanks = dict(self.tanks)
        if isinstance(self.owned_tanks, (str, bytes)):
            raise TypeError("owned_tanks must be a collection")
        owned = frozenset(text(item, "owned tank") for item in self.owned_tanks)
        global_fish_ids: set[str] = set()
        for key, tank in tanks.items():
            if not isinstance(tank, AquariumTankState):
                raise TypeError("tanks must contain AquariumTankState")
            if text(key, "tank key") != tank.tank_id:
                raise ValueError("tank key must match tank_id")
            for fish in tank.fish:
                if fish.id in global_fish_ids:
                    raise ValueError(f"duplicate fish identity across aquarium: {fish.id}")
                global_fish_ids.add(fish.id)
        if not set(tanks).issubset(owned):
            raise ValueError("every tank state must be owned")
        total = count(self.total_fish_displayed, "total fish displayed")
        if total != sum(len(tank.fish) for tank in tanks.values()):
            raise ValueError("total fish displayed must match tank contents")
        object.__setattr__(self, "tanks", tanks)
        object.__setattr__(self, "owned_tanks", owned)
        object.__setattr__(self, "owned_decorations", counts(self.owned_decorations, "owned decorations"))
        object.__setattr__(self, "total_fish_displayed", total)


@dataclass(frozen=True, slots=True)
class AquariumPurchasePlan:
    cost: Mapping[str, int]
    affordable: bool


@dataclass(frozen=True, slots=True)
class FishTransferPlan:
    aquarium: AquariumState
    fish_id: str
    tank_id: str


@dataclass(frozen=True, slots=True)
class DecorationPlacementPlan:
    aquarium: AquariumState
    placed: PlacedDecoration

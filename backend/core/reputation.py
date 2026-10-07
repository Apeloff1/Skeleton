"""Faction reputation kernel mined from Openworld4.

Generalizes faction levels, benefits, allied spillover and hostile penalties into
storage-neutral domain logic suitable for quests, NPCs, shops and live events.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ReputationBand:
    name: str
    min_value: int
    max_value: int


DEFAULT_BANDS = (
    ReputationBand("hated", -1000, -500),
    ReputationBand("hostile", -499, -200),
    ReputationBand("unfriendly", -199, -1),
    ReputationBand("neutral", 0, 499),
    ReputationBand("friendly", 500, 2999),
    ReputationBand("honored", 3000, 8999),
    ReputationBand("revered", 9000, 20999),
    ReputationBand("exalted", 21000, 999999),
)


@dataclass(frozen=True, slots=True)
class FactionDefinition:
    id: str
    allies: tuple[str, ...] = ()
    enemies: tuple[str, ...] = ()
    benefits: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(slots=True)
class ReputationState:
    factions: dict[str, FactionDefinition]
    values: dict[str, int] = field(default_factory=dict)
    bands: tuple[ReputationBand, ...] = DEFAULT_BANDS

    def __post_init__(self) -> None:
        for faction_id in self.factions:
            self.values.setdefault(faction_id, 0)

    def band_for_value(self, value: int) -> ReputationBand:
        for band in self.bands:
            if band.min_value <= value <= band.max_value:
                return band
        return self.bands[3]

    def band(self, faction_id: str) -> ReputationBand:
        self._require(faction_id)
        return self.band_for_value(self.values[faction_id])

    def _require(self, faction_id: str) -> FactionDefinition:
        try:
            return self.factions[faction_id]
        except KeyError as exc:
            raise KeyError(f"unknown faction {faction_id!r}") from exc

    def adjust(
        self,
        faction_id: str,
        delta: int,
        *,
        ally_ratio: float = 0.20,
        enemy_ratio: float = 0.25,
        floor: int = -1000,
        ceiling: int = 999999,
    ) -> dict[str, int]:
        faction = self._require(faction_id)
        changes: dict[str, int] = {}

        def apply(target: str, amount: int) -> None:
            if target not in self.factions or amount == 0:
                return
            before = self.values.get(target, 0)
            after = max(floor, min(ceiling, before + amount))
            self.values[target] = after
            changes[target] = after - before

        apply(faction_id, int(delta))
        if delta != 0:
            ally_delta = int(round(delta * ally_ratio))
            enemy_delta = -int(round(delta * enemy_ratio))
            for ally in faction.allies:
                apply(ally, ally_delta)
            for enemy in faction.enemies:
                apply(enemy, enemy_delta)
        return changes

    def benefits(self, faction_id: str) -> tuple[str, ...]:
        faction = self._require(faction_id)
        current = self.band(faction_id).name
        order = [band.name for band in self.bands]
        current_index = order.index(current)
        unlocked: list[str] = []
        by_band = dict(faction.benefits)
        for index, name in enumerate(order):
            if index <= current_index:
                unlocked.extend(by_band.get(name, ()))
        return tuple(dict.fromkeys(unlocked))

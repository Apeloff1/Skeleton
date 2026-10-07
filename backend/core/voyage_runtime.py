"""Sea-voyage runtime mined from Openworld4 and reduced to core simulation rules."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import ceil


class Hazard(StrEnum):
    NONE = "none"
    STORM = "storm"
    REEF = "reef"
    PIRATES = "pirates"
    MONSTER = "monster"


@dataclass(frozen=True, slots=True)
class VesselSpec:
    id: str
    tier: int
    speed: float
    durability: float
    cargo_capacity: int
    crew_capacity: int
    max_sea_minutes: float
    special_ability: str | None = None

    def __post_init__(self) -> None:
        if not self.id or self.tier < 1 or self.speed <= 0 or self.durability <= 0:
            raise ValueError("invalid vessel specification")
        if self.cargo_capacity < 0 or self.crew_capacity < 1 or self.max_sea_minutes <= 0:
            raise ValueError("invalid vessel capacity")


@dataclass(frozen=True, slots=True)
class VoyageLeg:
    id: str
    distance: float
    difficulty: int = 1
    hazard: Hazard = Hazard.NONE
    reward_gold: int = 0

    def __post_init__(self) -> None:
        if not self.id or self.distance <= 0 or self.difficulty < 1:
            raise ValueError("invalid voyage leg")


@dataclass(slots=True)
class VesselState:
    spec: VesselSpec
    hull: float | None = None
    food: float = 100.0
    water: float = 100.0
    morale: float = 100.0
    cargo: dict[str, int] = field(default_factory=dict)
    crew: int = 1
    sea_minutes: float = 0.0

    def __post_init__(self) -> None:
        self.hull = self.spec.durability if self.hull is None else self.hull
        if self.crew < 1 or self.crew > self.spec.crew_capacity:
            raise ValueError("crew outside vessel capacity")

    @property
    def cargo_used(self) -> int:
        return sum(max(0, int(v)) for v in self.cargo.values())

    def load(self, item: str, quantity: int) -> None:
        if not item or quantity <= 0:
            raise ValueError("item and positive quantity required")
        if self.cargo_used + quantity > self.spec.cargo_capacity:
            raise RuntimeError("cargo capacity exceeded")
        self.cargo[item] = self.cargo.get(item, 0) + quantity


@dataclass(frozen=True, slots=True)
class LegResult:
    completed: bool
    travel_minutes: float
    hull_damage: float
    food_used: float
    water_used: float
    morale_delta: float
    reward_gold: int
    reason: str


class VoyageSimulator:
    def __init__(self, state: VesselState) -> None:
        self.state = state
        self.completed_legs: list[str] = []
        self.gold = 0

    def _hazard_damage(self, leg: VoyageLeg) -> float:
        base = float(leg.difficulty * 2)
        ability = self.state.spec.special_ability or ""
        if leg.hazard is Hazard.NONE:
            return 0.0
        if leg.hazard is Hazard.STORM and ability in {"storm_resistant", "weather_control"}:
            return base * 0.25
        if leg.hazard is Hazard.REEF and ability in {"shallow_water_expert", "reef_harmony"}:
            return base * 0.25
        if leg.hazard is Hazard.PIRATES and ability in {"boarding_ready", "cannon_fishing", "master_of_seas"}:
            return base * 0.4
        if leg.hazard is Hazard.MONSTER and ability in {"monster_deterrent", "deep_dive", "master_of_seas"}:
            return base * 0.4
        return base * 1.5

    def run_leg(self, leg: VoyageLeg) -> LegResult:
        if self.state.hull is None or self.state.hull <= 0:
            return LegResult(False, 0, 0, 0, 0, 0, 0, "vessel disabled")
        speed_factor = max(0.5, self.state.morale / 100)
        effective_speed = self.state.spec.speed * speed_factor
        travel_minutes = leg.distance / effective_speed * 10
        if self.state.sea_minutes + travel_minutes > self.state.spec.max_sea_minutes:
            return LegResult(False, travel_minutes, 0, 0, 0, 0, 0, "sea-time limit exceeded")

        crew_factor = max(1, self.state.crew)
        food_used = travel_minutes * crew_factor * 0.06
        water_used = travel_minutes * crew_factor * 0.08
        if self.state.food < food_used:
            return LegResult(False, travel_minutes, 0, food_used, water_used, -10, 0, "insufficient food")
        if self.state.water < water_used:
            return LegResult(False, travel_minutes, 0, food_used, water_used, -15, 0, "insufficient water")

        damage = self._hazard_damage(leg)
        if damage >= self.state.hull:
            self.state.hull = 0
            self.state.food -= food_used
            self.state.water -= water_used
            self.state.sea_minutes += travel_minutes
            self.state.morale = max(0.0, self.state.morale - 20)
            return LegResult(False, travel_minutes, damage, food_used, water_used, -20, 0, "vessel lost")

        self.state.hull -= damage
        self.state.food -= food_used
        self.state.water -= water_used
        self.state.sea_minutes += travel_minutes
        morale_delta = -float(max(0, leg.difficulty - self.state.spec.tier)) * 2
        if leg.hazard is Hazard.NONE:
            morale_delta += 1
        self.state.morale = min(100.0, max(0.0, self.state.morale + morale_delta))
        self.completed_legs.append(leg.id)
        self.gold += leg.reward_gold
        return LegResult(True, travel_minutes, damage, food_used, water_used, morale_delta, leg.reward_gold, "completed")

    def repair(self, amount: float) -> float:
        if amount <= 0:
            raise ValueError("repair amount must be positive")
        assert self.state.hull is not None
        before = self.state.hull
        self.state.hull = min(self.state.spec.durability, self.state.hull + amount)
        return self.state.hull - before

    def resupply(self, *, food: float = 0, water: float = 0) -> None:
        if food < 0 or water < 0:
            raise ValueError("resupply cannot be negative")
        self.state.food = min(100.0, self.state.food + food)
        self.state.water = min(100.0, self.state.water + water)

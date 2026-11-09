"""Pure aquarium/display policy promoted from exact Lorebuffa/Openworld lineage.

Both source repositories carry the identical ``backend/aquarium_routes.py`` blob
``223f65a8b8cb4c60528e6c4cc585a01296178ea0``. FastAPI, Pydantic, Motor/Mongo,
wallet mutation, tacklebox persistence, UUID/random generation and source catalogs
remain source-owned. This module promotes only portable aquarium policy.

The frontier model deliberately derives counts from canonical state, validates
positions and identities, and uses quantity-aware decoration inventory so source
list/count drift cannot silently corrupt capacity or ownership decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
import math
from typing import Any, Mapping


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if normalized != value:
        raise ValueError(f"{field_name} must be normalized")
    return value


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
    return value


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _nonnegative_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")
    if numeric < 0:
        raise ValueError(f"{field_name} must not be negative")
    return numeric


def _aware(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _cost(values: Mapping[str, int], field_name: str = "cost") -> dict[str, int]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    normalized: dict[str, int] = {}
    for raw_currency, raw_amount in values.items():
        currency = _text(raw_currency, f"{field_name} currency")
        if currency in normalized:
            raise ValueError(f"duplicate {field_name} currency: {currency}")
        normalized[currency] = _nonnegative_int(
            raw_amount, f"{field_name} amount for {currency}"
        )
    return normalized


def _counts(values: Mapping[str, int], field_name: str) -> dict[str, int]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    normalized: dict[str, int] = {}
    for raw_id, raw_count in values.items():
        item_id = _text(raw_id, f"{field_name} id")
        count = _nonnegative_int(raw_count, f"{field_name} count for {item_id}")
        if count:
            normalized[item_id] = count
    return normalized


@dataclass(frozen=True, slots=True)
class AquariumPosition:
    """Normalized display position expressed in source-compatible percentages."""

    x: int
    y: int

    def __post_init__(self) -> None:
        x = _nonnegative_int(self.x, "aquarium position x")
        y = _nonnegative_int(self.y, "aquarium position y")
        if x > 100 or y > 100:
            raise ValueError("aquarium position coordinates must be within 0..100")
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)

    def as_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y}


@dataclass(frozen=True, slots=True)
class AquariumTankSpec:
    id: str
    name: str
    capacity: int
    width: int
    height: int
    decorations_allowed: int
    unlock_level: int = 1
    cost: Mapping[str, int] = field(default_factory=dict)
    special: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "tank id"))
        object.__setattr__(self, "name", _text(self.name, "tank name"))
        object.__setattr__(self, "capacity", _positive_int(self.capacity, "tank capacity"))
        object.__setattr__(self, "width", _positive_int(self.width, "tank width"))
        object.__setattr__(self, "height", _positive_int(self.height, "tank height"))
        object.__setattr__(
            self,
            "decorations_allowed",
            _nonnegative_int(self.decorations_allowed, "tank decorations_allowed"),
        )
        object.__setattr__(
            self, "unlock_level", _positive_int(self.unlock_level, "tank unlock_level")
        )
        object.__setattr__(self, "cost", _cost(self.cost, "tank cost"))
        if not isinstance(self.special, bool):
            raise TypeError("tank special must be boolean")


@dataclass(frozen=True, slots=True)
class AquariumDecorationSpec:
    id: str
    name: str
    category: str
    cost: Mapping[str, int]
    icon: str = ""
    animated: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "decoration id"))
        object.__setattr__(self, "name", _text(self.name, "decoration name"))
        object.__setattr__(
            self, "category", _text(self.category, "decoration category").lower()
        )
        object.__setattr__(self, "cost", _cost(self.cost, "decoration cost"))
        if not isinstance(self.icon, str):
            raise TypeError("decoration icon must be a string")
        if not isinstance(self.animated, bool):
            raise TypeError("decoration animated must be boolean")


@dataclass(frozen=True, slots=True)
class AquariumThemeSpec:
    id: str
    name: str
    primary: str
    secondary: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "theme id"))
        object.__setattr__(self, "name", _text(self.name, "theme name"))
        object.__setattr__(self, "primary", _text(self.primary, "theme primary"))
        object.__setattr__(self, "secondary", _text(self.secondary, "theme secondary"))


@dataclass(frozen=True, slots=True)
class DisplayFish:
    id: str
    name: str
    species: str
    size: float
    color: str
    traits: Mapping[str, Any]
    position: AquariumPosition
    added_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "display fish id"))
        object.__setattr__(self, "name", _text(self.name, "display fish name"))
        object.__setattr__(self, "species", _text(self.species, "display fish species"))
        object.__setattr__(
            self, "size", _nonnegative_number(self.size, "display fish size")
        )
        object.__setattr__(self, "color", _text(self.color, "display fish color"))
        if not isinstance(self.traits, Mapping):
            raise TypeError("display fish traits must be a mapping")
        object.__setattr__(self, "traits", dict(self.traits))
        if not isinstance(self.position, AquariumPosition):
            raise TypeError("display fish position must be AquariumPosition")
        object.__setattr__(
            self, "added_at", _aware(self.added_at, "display fish added_at")
        )


@dataclass(frozen=True, slots=True)
class PlacedDecoration:
    id: str
    decoration_id: str
    name: str
    icon: str
    position: AquariumPosition
    placed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "placed decoration id"))
        object.__setattr__(
            self,
            "decoration_id",
            _text(self.decoration_id, "placed decoration decoration_id"),
        )
        object.__setattr__(
            self, "name", _text(self.name, "placed decoration name")
        )
        if not isinstance(self.icon, str):
            raise TypeError("placed decoration icon must be a string")
        if not isinstance(self.position, AquariumPosition):
            raise TypeError("placed decoration position must be AquariumPosition")
        object.__setattr__(
            self, "placed_at", _aware(self.placed_at, "placed decoration placed_at")
        )


@dataclass(frozen=True, slots=True)
class AquariumTankState:
    tank_id: str
    fish: tuple[DisplayFish, ...] = ()
    decorations: tuple[PlacedDecoration, ...] = ()
    theme: str = "ocean"
    background: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tank_id", _text(self.tank_id, "tank state tank_id"))
        fish_ids: set[str] = set()
        for fish in self.fish:
            if not isinstance(fish, DisplayFish):
                raise TypeError("tank fish must contain DisplayFish values")
            if fish.id in fish_ids:
                raise ValueError(f"duplicate fish id in tank: {fish.id}")
            fish_ids.add(fish.id)
        decoration_ids: set[str] = set()
        for decoration in self.decorations:
            if not isinstance(decoration, PlacedDecoration):
                raise TypeError(
                    "tank decorations must contain PlacedDecoration values"
                )
            if decoration.id in decoration_ids:
                raise ValueError(
                    f"duplicate placed decoration id in tank: {decoration.id}"
                )
            decoration_ids.add(decoration.id)
        object.__setattr__(self, "fish", tuple(self.fish))
        object.__setattr__(self, "decorations", tuple(self.decorations))
        object.__setattr__(self, "theme", _text(self.theme, "tank state theme"))
        if self.background is not None:
            object.__setattr__(
                self,
                "background",
                _text(self.background, "tank state background"),
            )


@dataclass(frozen=True, slots=True)
class AquariumState:
    tanks: Mapping[str, AquariumTankState]
    owned_tanks: frozenset[str]
    owned_decorations: Mapping[str, int] = field(default_factory=dict)
    visitors: int = 0
    likes: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.tanks, Mapping):
            raise TypeError("aquarium tanks must be a mapping")
        normalized_tanks: dict[str, AquariumTankState] = {}
        global_fish_ids: set[str] = set()
        global_placement_ids: set[str] = set()
        for raw_id, tank in self.tanks.items():
            tank_id = _text(raw_id, "aquarium tank key")
            if not isinstance(tank, AquariumTankState):
                raise TypeError("aquarium tanks must contain AquariumTankState values")
            if tank.tank_id != tank_id:
                raise ValueError("aquarium tank key must match tank_id")
            if tank_id in normalized_tanks:
                raise ValueError(f"duplicate aquarium tank id: {tank_id}")
            for fish in tank.fish:
                if fish.id in global_fish_ids:
                    raise ValueError(f"fish id appears in multiple tanks: {fish.id}")
                global_fish_ids.add(fish.id)
            for decoration in tank.decorations:
                if decoration.id in global_placement_ids:
                    raise ValueError(
                        f"placed decoration id appears in multiple tanks: {decoration.id}"
                    )
                global_placement_ids.add(decoration.id)
            normalized_tanks[tank_id] = tank

        if isinstance(self.owned_tanks, (str, bytes)):
            raise TypeError("owned_tanks must be a collection of strings")
        normalized_owned: set[str] = set()
        for raw_id in self.owned_tanks:
            tank_id = _text(raw_id, "owned tank id")
            if tank_id in normalized_owned:
                raise ValueError(f"duplicate owned tank id: {tank_id}")
            normalized_owned.add(tank_id)
        if set(normalized_tanks) != normalized_owned:
            raise ValueError("owned_tanks must exactly match materialized tank state")

        object.__setattr__(self, "tanks", normalized_tanks)
        object.__setattr__(self, "owned_tanks", frozenset(normalized_owned))
        object.__setattr__(
            self,
            "owned_decorations",
            _counts(self.owned_decorations, "owned decorations"),
        )
        object.__setattr__(
            self, "visitors", _nonnegative_int(self.visitors, "aquarium visitors")
        )
        object.__setattr__(self, "likes", _nonnegative_int(self.likes, "aquarium likes"))

    @property
    def total_fish_displayed(self) -> int:
        return sum(len(tank.fish) for tank in self.tanks.values())

    @property
    def total_decorations_placed(self) -> int:
        return sum(len(tank.decorations) for tank in self.tanks.values())


@dataclass(frozen=True, slots=True)
class AquariumPurchasePlan:
    aquarium: AquariumState
    cost: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class FishMovePlan:
    aquarium: AquariumState
    fish: DisplayFish
    tank_id: str


@dataclass(frozen=True, slots=True)
class DecorationPlacementPlan:
    aquarium: AquariumState
    placement: PlacedDecoration
    tank_id: str


@dataclass(frozen=True, slots=True)
class AquariumLikeLedger:
    """Per-owner daily like identities kept separate from display state."""

    entries: frozenset[tuple[str, date]] = frozenset()

    def __post_init__(self) -> None:
        normalized: set[tuple[str, date]] = set()
        for liker_id, liked_on in self.entries:
            liker = _text(liker_id, "aquarium liker id")
            if not isinstance(liked_on, date) or isinstance(liked_on, datetime):
                raise TypeError("aquarium like date must be a date")
            normalized.add((liker, liked_on))
        object.__setattr__(self, "entries", frozenset(normalized))


def tank_from_record(record: Mapping[str, Any]) -> AquariumTankSpec:
    if not isinstance(record, Mapping):
        raise TypeError("tank record must be a mapping")
    size = record.get("size")
    if not isinstance(size, Mapping):
        raise TypeError("tank size must be a mapping")
    raw_cost = record.get("cost", {})
    if raw_cost in (None, 0):
        raw_cost = {}
    if not isinstance(raw_cost, Mapping):
        raise TypeError("tank cost must be a mapping or zero")
    return AquariumTankSpec(
        id=_text(record.get("id"), "tank id"),
        name=_text(record.get("name"), "tank name"),
        capacity=_positive_int(record.get("capacity"), "tank capacity"),
        width=_positive_int(size.get("width"), "tank width"),
        height=_positive_int(size.get("height"), "tank height"),
        decorations_allowed=_nonnegative_int(
            record.get("decorations_allowed"), "tank decorations_allowed"
        ),
        unlock_level=_positive_int(record.get("unlock_level", 1), "tank unlock_level"),
        cost=_cost(raw_cost, "tank cost"),
        special=record.get("special", False),
    )


def decoration_from_record(record: Mapping[str, Any]) -> AquariumDecorationSpec:
    if not isinstance(record, Mapping):
        raise TypeError("decoration record must be a mapping")
    raw_cost = record.get("cost", {})
    if not isinstance(raw_cost, Mapping):
        raise TypeError("decoration cost must be a mapping")
    icon = record.get("icon", "")
    if not isinstance(icon, str):
        raise TypeError("decoration icon must be a string")
    return AquariumDecorationSpec(
        id=_text(record.get("id"), "decoration id"),
        name=_text(record.get("name"), "decoration name"),
        category=_text(record.get("category"), "decoration category"),
        cost=_cost(raw_cost, "decoration cost"),
        icon=icon,
        animated=record.get("animated", False),
    )


def theme_from_record(record: Mapping[str, Any]) -> AquariumThemeSpec:
    if not isinstance(record, Mapping):
        raise TypeError("theme record must be a mapping")
    colors = record.get("colors")
    if not isinstance(colors, Mapping):
        raise TypeError("theme colors must be a mapping")
    return AquariumThemeSpec(
        id=_text(record.get("id"), "theme id"),
        name=_text(record.get("name"), "theme name"),
        primary=_text(colors.get("primary"), "theme primary"),
        secondary=_text(colors.get("secondary"), "theme secondary"),
    )


def initial_aquarium(*, default_theme: str = "ocean") -> AquariumState:
    theme = _text(default_theme, "default theme")
    starter = AquariumTankState(tank_id="starter", theme=theme)
    return AquariumState(
        tanks={"starter": starter},
        owned_tanks=frozenset({"starter"}),
    )


def affordability_shortfall(
    cost: Mapping[str, int],
    balances: Mapping[str, int],
) -> Mapping[str, int]:
    normalized_cost = _cost(cost)
    normalized_balances = _counts(balances, "balances")
    missing: dict[str, int] = {}
    for currency, amount in normalized_cost.items():
        available = normalized_balances.get(currency, 0)
        if available < amount:
            missing[currency] = amount - available
    return missing


def _require_affordable(
    cost: Mapping[str, int],
    balances: Mapping[str, int],
) -> dict[str, int]:
    missing = dict(affordability_shortfall(cost, balances))
    if missing:
        details = ", ".join(
            f"{currency}:{amount}" for currency, amount in sorted(missing.items())
        )
        raise ValueError(f"insufficient aquarium purchase balance: {details}")
    return _cost(cost)


def purchase_tank(
    state: AquariumState,
    tank: AquariumTankSpec,
    *,
    user_level: int,
    balances: Mapping[str, int],
    default_theme: str = "ocean",
) -> AquariumPurchasePlan:
    if not isinstance(state, AquariumState):
        raise TypeError("state must be AquariumState")
    if not isinstance(tank, AquariumTankSpec):
        raise TypeError("tank must be AquariumTankSpec")
    level = _positive_int(user_level, "aquarium user_level")
    if tank.id in state.owned_tanks:
        raise ValueError(f"aquarium tank already owned: {tank.id}")
    if level < tank.unlock_level:
        raise ValueError(
            f"aquarium tank {tank.id} requires level {tank.unlock_level}"
        )
    cost = _require_affordable(tank.cost, balances)
    tanks = dict(state.tanks)
    tanks[tank.id] = AquariumTankState(
        tank_id=tank.id,
        theme=_text(default_theme, "default theme"),
    )
    return AquariumPurchasePlan(
        aquarium=replace(
            state,
            tanks=tanks,
            owned_tanks=frozenset((*state.owned_tanks, tank.id)),
        ),
        cost=cost,
    )


def purchase_decoration(
    state: AquariumState,
    decoration: AquariumDecorationSpec,
    *,
    balances: Mapping[str, int],
    quantity: int = 1,
) -> AquariumPurchasePlan:
    if not isinstance(state, AquariumState):
        raise TypeError("state must be AquariumState")
    if not isinstance(decoration, AquariumDecorationSpec):
        raise TypeError("decoration must be AquariumDecorationSpec")
    count = _positive_int(quantity, "decoration purchase quantity")
    total_cost = {
        currency: amount * count for currency, amount in decoration.cost.items()
    }
    cost = _require_affordable(total_cost, balances)
    owned = dict(state.owned_decorations)
    owned[decoration.id] = owned.get(decoration.id, 0) + count
    return AquariumPurchasePlan(
        aquarium=replace(state, owned_decorations=owned),
        cost=cost,
    )


def display_fish_from_record(
    record: Mapping[str, Any],
    *,
    position: AquariumPosition,
    added_at: datetime,
) -> DisplayFish:
    if not isinstance(record, Mapping):
        raise TypeError("fish record must be a mapping")
    if not isinstance(position, AquariumPosition):
        raise TypeError("position must be AquariumPosition")
    name = record.get("name", "Fish")
    if not isinstance(name, str):
        raise TypeError("fish name must be a string")
    normalized_name = name.strip() or "Fish"
    raw_species = record.get("species")
    if raw_species is None:
        raw_species = normalized_name.lower().replace(" ", "_")
    traits = record.get("traits", {})
    if not isinstance(traits, Mapping):
        raise TypeError("fish traits must be a mapping")
    color = record.get("color", "#4A90D9")
    if not isinstance(color, str):
        raise TypeError("fish color must be a string")
    return DisplayFish(
        id=_text(record.get("id"), "fish id"),
        name=_text(normalized_name, "fish name"),
        species=_text(raw_species, "fish species"),
        size=_nonnegative_number(record.get("size", 30), "fish size"),
        color=_text(color, "fish color"),
        traits=dict(traits),
        position=position,
        added_at=added_at,
    )


def add_fish(
    state: AquariumState,
    tank: AquariumTankSpec,
    fish: DisplayFish,
) -> FishMovePlan:
    if not isinstance(state, AquariumState):
        raise TypeError("state must be AquariumState")
    if not isinstance(tank, AquariumTankSpec):
        raise TypeError("tank must be AquariumTankSpec")
    if not isinstance(fish, DisplayFish):
        raise TypeError("fish must be DisplayFish")
    if tank.id not in state.owned_tanks:
        raise ValueError(f"aquarium tank not owned: {tank.id}")
    tank_state = state.tanks.get(tank.id)
    if tank_state is None:
        raise ValueError(f"aquarium tank state missing: {tank.id}")
    if len(tank_state.fish) >= tank.capacity:
        raise ValueError(f"aquarium tank is at capacity: {tank.id}")
    if any(
        existing.id == fish.id
        for existing_tank in state.tanks.values()
        for existing in existing_tank.fish
    ):
        raise ValueError(f"fish already displayed: {fish.id}")
    next_tank = replace(tank_state, fish=(*tank_state.fish, fish))
    tanks = dict(state.tanks)
    tanks[tank.id] = next_tank
    return FishMovePlan(
        aquarium=replace(state, tanks=tanks),
        fish=fish,
        tank_id=tank.id,
    )


def remove_fish(state: AquariumState, *, fish_id: str) -> FishMovePlan:
    if not isinstance(state, AquariumState):
        raise TypeError("state must be AquariumState")
    target_id = _text(fish_id, "fish_id")
    for tank_id, tank in state.tanks.items():
        for fish in tank.fish:
            if fish.id != target_id:
                continue
            next_tank = replace(
                tank,
                fish=tuple(item for item in tank.fish if item.id != target_id),
            )
            tanks = dict(state.tanks)
            tanks[tank_id] = next_tank
            return FishMovePlan(
                aquarium=replace(state, tanks=tanks),
                fish=fish,
                tank_id=tank_id,
            )
    raise ValueError(f"fish not found in aquarium: {target_id}")


def place_decoration(
    state: AquariumState,
    tank: AquariumTankSpec,
    decoration: AquariumDecorationSpec,
    *,
    placement_id: str,
    position: AquariumPosition,
    placed_at: datetime,
) -> DecorationPlacementPlan:
    if not isinstance(state, AquariumState):
        raise TypeError("state must be AquariumState")
    if not isinstance(tank, AquariumTankSpec):
        raise TypeError("tank must be AquariumTankSpec")
    if not isinstance(decoration, AquariumDecorationSpec):
        raise TypeError("decoration must be AquariumDecorationSpec")
    if not isinstance(position, AquariumPosition):
        raise TypeError("position must be AquariumPosition")
    placement_key = _text(placement_id, "placement_id")
    if state.owned_decorations.get(decoration.id, 0) < 1:
        raise ValueError(f"decoration not owned: {decoration.id}")
    tank_state = state.tanks.get(tank.id)
    if tank_state is None or tank.id not in state.owned_tanks:
        raise ValueError(f"aquarium tank not owned: {tank.id}")
    if len(tank_state.decorations) >= tank.decorations_allowed:
        raise ValueError(f"maximum decorations reached for tank: {tank.id}")
    if any(
        placed.id == placement_key
        for existing_tank in state.tanks.values()
        for placed in existing_tank.decorations
    ):
        raise ValueError(f"duplicate placement id: {placement_key}")
    placement = PlacedDecoration(
        id=placement_key,
        decoration_id=decoration.id,
        name=decoration.name,
        icon=decoration.icon,
        position=position,
        placed_at=placed_at,
    )
    next_tank = replace(
        tank_state, decorations=(*tank_state.decorations, placement)
    )
    tanks = dict(state.tanks)
    tanks[tank.id] = next_tank
    owned = dict(state.owned_decorations)
    remaining = owned[decoration.id] - 1
    if remaining:
        owned[decoration.id] = remaining
    else:
        owned.pop(decoration.id)
    return DecorationPlacementPlan(
        aquarium=replace(state, tanks=tanks, owned_decorations=owned),
        placement=placement,
        tank_id=tank.id,
    )


def set_theme(
    state: AquariumState,
    *,
    tank_id: str,
    theme: AquariumThemeSpec,
) -> AquariumState:
    if not isinstance(state, AquariumState):
        raise TypeError("state must be AquariumState")
    if not isinstance(theme, AquariumThemeSpec):
        raise TypeError("theme must be AquariumThemeSpec")
    target = _text(tank_id, "tank_id")
    if target not in state.owned_tanks:
        raise ValueError(f"aquarium tank not owned: {target}")
    tank = state.tanks.get(target)
    if tank is None:
        raise ValueError(f"aquarium tank state missing: {target}")
    tanks = dict(state.tanks)
    tanks[target] = replace(tank, theme=theme.id)
    return replace(state, tanks=tanks)


def record_visit(state: AquariumState) -> AquariumState:
    if not isinstance(state, AquariumState):
        raise TypeError("state must be AquariumState")
    return replace(state, visitors=state.visitors + 1)


def record_like(
    state: AquariumState,
    ledger: AquariumLikeLedger,
    *,
    liker_id: str,
    liked_on: date,
) -> tuple[AquariumState, AquariumLikeLedger]:
    if not isinstance(state, AquariumState):
        raise TypeError("state must be AquariumState")
    if not isinstance(ledger, AquariumLikeLedger):
        raise TypeError("ledger must be AquariumLikeLedger")
    liker = _text(liker_id, "liker_id")
    if not isinstance(liked_on, date) or isinstance(liked_on, datetime):
        raise TypeError("liked_on must be a date")
    key = (liker, liked_on)
    if key in ledger.entries:
        raise ValueError("aquarium already liked by this identity today")
    return (
        replace(state, likes=state.likes + 1),
        AquariumLikeLedger(entries=frozenset((*ledger.entries, key))),
    )

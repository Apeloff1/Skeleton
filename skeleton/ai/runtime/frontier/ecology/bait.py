"""Pure bait and fishing-spot policy from exact shared Lorebuffa/Openworld lineage.

Both source repositories use ``backend/bait_routes.py`` blob
``9963db63e814d84b6292ecc0cc4fe3c2b2b077e8``. Catalogs, FastAPI, MongoDB,
wallet mutation, inventory mutation and catch-stat persistence remain source-owned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class BaitSpec:
    id: str
    name: str
    rarity: str
    durability: int
    cost: Mapping[str, int] = field(default_factory=dict)
    catch_bonus: float = 1.0
    rare_bonus: float = 1.0
    legendary_bonus: float = 1.0
    storm_bonus: float | None = None
    night_bonus: float | None = None
    effective_fish: tuple[str, ...] = ()
    limited: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _token(self.id, "bait id"))
        object.__setattr__(self, "name", _text(self.name, "bait name"))
        object.__setattr__(self, "rarity", _token(self.rarity, "bait rarity"))
        object.__setattr__(self, "durability", _positive_int(self.durability, "bait durability"))
        object.__setattr__(self, "cost", _currency_map(self.cost, "bait cost"))
        for field_name in ("catch_bonus", "rare_bonus", "legendary_bonus"):
            object.__setattr__(
                self,
                field_name,
                _nonnegative_number(getattr(self, field_name), f"bait {field_name}"),
            )
        for field_name in ("storm_bonus", "night_bonus"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _nonnegative_number(value, f"bait {field_name}"),
                )
        effective = tuple(_token(value, "effective fish") for value in self.effective_fish)
        if len(set(effective)) != len(effective):
            raise ValueError("effective fish entries must be unique")
        object.__setattr__(self, "effective_fish", effective)
        if not isinstance(self.limited, bool):
            raise TypeError("bait limited must be a boolean")


@dataclass(frozen=True, slots=True)
class FishingSpotSpec:
    id: str
    name: str
    difficulty: int
    unlock_level: int
    bonuses: Mapping[str, float] = field(default_factory=dict)
    requires_boat: bool = False
    requires_item: str | None = None
    hidden: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _token(self.id, "spot id"))
        object.__setattr__(self, "name", _text(self.name, "spot name"))
        object.__setattr__(self, "difficulty", _positive_int(self.difficulty, "spot difficulty"))
        object.__setattr__(self, "unlock_level", _positive_int(self.unlock_level, "spot unlock level"))
        if not isinstance(self.bonuses, Mapping):
            raise TypeError("spot bonuses must be a mapping")
        bonuses: dict[str, float] = {}
        for raw_key, raw_value in self.bonuses.items():
            key = _token(raw_key, "spot bonus")
            if key in bonuses:
                raise ValueError(f"duplicate spot bonus: {key}")
            bonuses[key] = _nonnegative_number(raw_value, f"spot bonus {key}")
        object.__setattr__(self, "bonuses", bonuses)
        if not isinstance(self.requires_boat, bool):
            raise TypeError("requires_boat must be a boolean")
        if self.requires_item is not None:
            object.__setattr__(self, "requires_item", _token(self.requires_item, "required item"))
        if not isinstance(self.hidden, bool):
            raise TypeError("spot hidden must be a boolean")


@dataclass(frozen=True, slots=True)
class BaitLoadout:
    equipped_bait: str | None = None
    uses_remaining: int = 0

    def __post_init__(self) -> None:
        if self.equipped_bait is not None:
            object.__setattr__(self, "equipped_bait", _token(self.equipped_bait, "equipped bait"))
        object.__setattr__(
            self,
            "uses_remaining",
            _nonnegative_int(self.uses_remaining, "bait uses remaining"),
        )
        if self.equipped_bait is None and self.uses_remaining != 0:
            raise ValueError("bait uses require an equipped bait")


@dataclass(frozen=True, slots=True)
class BaitEquipPlan:
    bait_id: str
    next_loadout: BaitLoadout
    inventory_decrement: int = 1


@dataclass(frozen=True, slots=True)
class BaitUsePlan:
    next_loadout: BaitLoadout
    bait_used: bool
    bait_depleted: bool
    catch_bonus: float
    rare_bonus: float


@dataclass(frozen=True, slots=True)
class CatchBonuses:
    catch_rate: float = 1.0
    rare_chance: float = 1.0
    legendary_chance: float = 1.0
    xp_multiplier: float = 1.0
    coin_multiplier: float = 1.0

    def __post_init__(self) -> None:
        for field_name in (
            "catch_rate",
            "rare_chance",
            "legendary_chance",
            "xp_multiplier",
            "coin_multiplier",
        ):
            object.__setattr__(
                self,
                field_name,
                _nonnegative_number(getattr(self, field_name), field_name),
            )


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _token(value: object, field_name: str) -> str:
    return _text(value, field_name).lower()


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _positive_int(value: object, field_name: str) -> int:
    value = _nonnegative_int(value, field_name)
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
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


def _currency_map(value: Mapping[str, int], field_name: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    result: dict[str, int] = {}
    for raw_currency, raw_amount in value.items():
        currency = _token(raw_currency, "currency")
        if currency in result:
            raise ValueError(f"duplicate currency: {currency}")
        result[currency] = _nonnegative_int(raw_amount, f"{currency} amount")
    return result


def bait_from_record(record: Mapping[str, Any]) -> BaitSpec:
    if not isinstance(record, Mapping):
        raise TypeError("bait record must be a mapping")
    effective = record.get("effective_fish", ())
    if isinstance(effective, (str, bytes)) or not isinstance(effective, Sequence):
        raise TypeError("effective_fish must be a sequence")
    limited = record.get("limited", False)
    if not isinstance(limited, bool):
        raise TypeError("bait limited must be a boolean")
    return BaitSpec(
        id=_token(record.get("id"), "bait id"),
        name=_text(record.get("name"), "bait name"),
        rarity=_token(record.get("rarity", "common"), "bait rarity"),
        durability=_positive_int(record.get("durability"), "bait durability"),
        cost=_currency_map(record.get("cost", {}), "bait cost"),
        catch_bonus=_nonnegative_number(record.get("catch_bonus", 1.0), "bait catch bonus"),
        rare_bonus=_nonnegative_number(record.get("rare_bonus", 1.0), "bait rare bonus"),
        legendary_bonus=_nonnegative_number(
            record.get("legendary_bonus", 1.0), "bait legendary bonus"
        ),
        storm_bonus=(
            None
            if record.get("storm_bonus") is None
            else _nonnegative_number(record["storm_bonus"], "bait storm bonus")
        ),
        night_bonus=(
            None
            if record.get("night_bonus") is None
            else _nonnegative_number(record["night_bonus"], "bait night bonus")
        ),
        effective_fish=tuple(_token(value, "effective fish") for value in effective),
        limited=limited,
    )


def spot_from_record(record: Mapping[str, Any]) -> FishingSpotSpec:
    if not isinstance(record, Mapping):
        raise TypeError("fishing spot record must be a mapping")
    bonuses = record.get("bonuses", {})
    if not isinstance(bonuses, Mapping):
        raise TypeError("spot bonuses must be a mapping")
    requires_boat = record.get("requires_boat", False)
    hidden = record.get("hidden", False)
    if not isinstance(requires_boat, bool) or not isinstance(hidden, bool):
        raise TypeError("spot boolean fields must be booleans")
    return FishingSpotSpec(
        id=_token(record.get("id"), "spot id"),
        name=_text(record.get("name"), "spot name"),
        difficulty=_positive_int(record.get("difficulty"), "spot difficulty"),
        unlock_level=_positive_int(record.get("unlock_level"), "spot unlock level"),
        bonuses={
            _token(key, "spot bonus"): _nonnegative_number(value, f"spot bonus {key}")
            for key, value in bonuses.items()
        },
        requires_boat=requires_boat,
        requires_item=(
            None
            if record.get("requires_item") is None
            else _token(record["requires_item"], "required item")
        ),
        hidden=hidden,
    )


def bait_purchase_cost(bait: BaitSpec, quantity: int) -> Mapping[str, int]:
    count = _positive_int(quantity, "bait purchase quantity")
    return {currency: amount * count for currency, amount in bait.cost.items()}


def can_afford_cost(wallet: Mapping[str, int], cost: Mapping[str, int]) -> bool:
    if not isinstance(wallet, Mapping):
        raise TypeError("wallet must be a mapping")
    normalized_wallet = _currency_map(wallet, "wallet")
    normalized_cost = _currency_map(cost, "cost")
    return all(normalized_wallet.get(currency, 0) >= amount for currency, amount in normalized_cost.items())


def equip_bait(
    current: BaitLoadout,
    bait: BaitSpec,
    *,
    owned_quantity: int,
) -> BaitEquipPlan:
    _ = current
    quantity = _nonnegative_int(owned_quantity, "owned bait quantity")
    if quantity < 1:
        raise ValueError("no bait of this type is owned")
    return BaitEquipPlan(
        bait_id=bait.id,
        next_loadout=BaitLoadout(
            equipped_bait=bait.id,
            uses_remaining=bait.durability,
        ),
    )


def use_bait(loadout: BaitLoadout, bait: BaitSpec | None) -> BaitUsePlan:
    if loadout.equipped_bait is None:
        if bait is not None:
            raise ValueError("bait spec supplied without an equipped bait")
        return BaitUsePlan(
            next_loadout=loadout,
            bait_used=False,
            bait_depleted=False,
            catch_bonus=1.0,
            rare_bonus=1.0,
        )
    if bait is None or bait.id != loadout.equipped_bait:
        raise ValueError("equipped bait must resolve to the matching bait spec")
    if loadout.uses_remaining <= 0:
        return BaitUsePlan(
            next_loadout=BaitLoadout(),
            bait_used=False,
            bait_depleted=True,
            catch_bonus=1.0,
            rare_bonus=1.0,
        )
    remaining = loadout.uses_remaining - 1
    return BaitUsePlan(
        next_loadout=(
            BaitLoadout()
            if remaining == 0
            else BaitLoadout(equipped_bait=bait.id, uses_remaining=remaining)
        ),
        bait_used=True,
        bait_depleted=remaining == 0,
        catch_bonus=bait.catch_bonus,
        rare_bonus=bait.rare_bonus,
    )


def bait_effective_for_fish(bait: BaitSpec, fish_type: str) -> bool:
    fish = _token(fish_type, "fish type")
    return "all" in bait.effective_fish or fish in bait.effective_fish


def calculate_catch_bonuses(
    bait: BaitSpec | None,
    spot: FishingSpotSpec | None,
    *,
    is_night: bool = False,
    is_storm: bool = False,
) -> CatchBonuses:
    if not isinstance(is_night, bool) or not isinstance(is_storm, bool):
        raise TypeError("fishing conditions must be booleans")

    catch_rate = 1.0
    rare_chance = 1.0
    legendary_chance = 1.0
    xp_multiplier = 1.0
    coin_multiplier = 1.0

    if bait is not None:
        catch_rate *= bait.catch_bonus
        rare_chance *= bait.rare_bonus
        legendary_chance *= bait.legendary_bonus
        if is_storm and bait.storm_bonus is not None:
            catch_rate *= bait.storm_bonus
        if is_night and bait.night_bonus is not None:
            rare_chance *= bait.night_bonus

    if spot is not None:
        xp_multiplier *= spot.bonuses.get("xp", 1.0)
        coin_multiplier *= spot.bonuses.get("coins", 1.0)
        rare_chance *= spot.bonuses.get("rare_chance", 1.0)
        legendary_chance *= spot.bonuses.get("legendary_chance", 1.0)

    return CatchBonuses(
        catch_rate=catch_rate,
        rare_chance=rare_chance,
        legendary_chance=legendary_chance,
        xp_multiplier=xp_multiplier,
        coin_multiplier=coin_multiplier,
    )


def spot_unlock_requirements(
    spot: FishingSpotSpec,
    *,
    player_level: int,
    unlocked_spots: Sequence[str] = (),
    has_boat: bool = False,
    inventory_items: Sequence[str] = (),
) -> tuple[str, ...]:
    level = _positive_int(player_level, "player level")
    if isinstance(unlocked_spots, (str, bytes)) or isinstance(inventory_items, (str, bytes)):
        raise TypeError("spot and inventory collections must be sequences")
    if not isinstance(has_boat, bool):
        raise TypeError("has_boat must be a boolean")
    unlocked = {_token(value, "unlocked spot") for value in unlocked_spots}
    items = {_token(value, "inventory item") for value in inventory_items}
    missing: list[str] = []
    if spot.id in unlocked:
        missing.append("already_unlocked")
    if level < spot.unlock_level:
        missing.append(f"level:{spot.unlock_level}")
    if spot.requires_boat and not has_boat:
        missing.append("boat")
    if spot.requires_item is not None and spot.requires_item not in items:
        missing.append(f"item:{spot.requires_item}")
    return tuple(missing)


def can_unlock_spot(
    spot: FishingSpotSpec,
    *,
    player_level: int,
    unlocked_spots: Sequence[str] = (),
    has_boat: bool = False,
    inventory_items: Sequence[str] = (),
) -> bool:
    return not spot_unlock_requirements(
        spot,
        player_level=player_level,
        unlocked_spots=unlocked_spots,
        has_boat=has_boat,
        inventory_items=inventory_items,
    )


def select_spot(spot_id: str, unlocked_spots: Sequence[str]) -> str:
    spot = _token(spot_id, "spot id")
    if isinstance(unlocked_spots, (str, bytes)):
        raise TypeError("unlocked spots must be a sequence")
    unlocked = {_token(value, "unlocked spot") for value in unlocked_spots}
    if spot not in unlocked:
        raise ValueError("spot is not unlocked")
    return spot


def combine_external_bonuses(
    fishing: CatchBonuses,
    external: Mapping[str, float],
) -> CatchBonuses:
    """Compose equipment/other provider-neutral bonus projections multiplicatively."""

    if not isinstance(external, Mapping):
        raise TypeError("external bonuses must be a mapping")
    allowed = {
        "catch_rate",
        "rare_chance",
        "legendary_chance",
        "xp_multiplier",
        "coin_multiplier",
    }
    normalized: dict[str, float] = {}
    for raw_key, raw_value in external.items():
        key = _token(raw_key, "external bonus")
        if key not in allowed:
            continue
        normalized[key] = _nonnegative_number(raw_value, f"external bonus {key}")
    return CatchBonuses(
        catch_rate=fishing.catch_rate * normalized.get("catch_rate", 1.0),
        rare_chance=fishing.rare_chance * normalized.get("rare_chance", 1.0),
        legendary_chance=fishing.legendary_chance * normalized.get("legendary_chance", 1.0),
        xp_multiplier=fishing.xp_multiplier * normalized.get("xp_multiplier", 1.0),
        coin_multiplier=fishing.coin_multiplier * normalized.get("coin_multiplier", 1.0),
    )

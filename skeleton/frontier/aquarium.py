"""Pure aquarium transitions promoted from exact shared Lorebuffa/Openworld lineage."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

from skeleton.frontier.aquarium_models import AquariumPosition, AquariumTankSpec, DecorationSpec, DisplayFish, aware, count, counts, text
from skeleton.frontier.aquarium_state import AquariumPurchasePlan, AquariumState, AquariumTankState, DecorationPlacementPlan, FishTransferPlan, PlacedDecoration


def initial_aquarium() -> AquariumState:
    return AquariumState({"starter": AquariumTankState("starter")}, frozenset({"starter"}))


def tank_from_record(record: Mapping[str, Any]) -> AquariumTankSpec:
    if not isinstance(record, Mapping):
        raise TypeError("tank record must be a mapping")
    raw_cost = {} if record.get("cost", {}) == 0 else record.get("cost", {})
    if not isinstance(raw_cost, Mapping):
        raise TypeError("tank cost must be a mapping or zero")
    return AquariumTankSpec(
        text(record.get("id"), "tank id"),
        text(record.get("name"), "tank name"),
        count(record.get("capacity"), "capacity", positive=True),
        count(record.get("unlock_level", 1), "unlock level", positive=True),
        count(record.get("decorations_allowed", 0), "decoration limit"),
        dict(raw_cost),
        record.get("special", False),
    )


def decoration_from_record(record: Mapping[str, Any]) -> DecorationSpec:
    if not isinstance(record, Mapping) or not isinstance(record.get("cost", {}), Mapping):
        raise TypeError("decoration record and cost must be mappings")
    return DecorationSpec(
        text(record.get("id"), "decoration id"),
        text(record.get("name"), "decoration name"),
        text(record.get("category"), "decoration category"),
        dict(record.get("cost", {})),
    )


def quote_purchase(cost: Mapping[str, int], wallet: Mapping[str, int]) -> AquariumPurchasePlan:
    normalized_cost, normalized_wallet = counts(cost, "purchase cost"), counts(wallet, "wallet")
    return AquariumPurchasePlan(normalized_cost, all(normalized_wallet.get(key, 0) >= value for key, value in normalized_cost.items()))


def quote_tank_purchase(state: AquariumState, tank: AquariumTankSpec, *, user_level: int, wallet: Mapping[str, int]) -> AquariumPurchasePlan:
    if tank.id in state.owned_tanks:
        raise ValueError("tank already owned")
    if count(user_level, "user level", positive=True) < tank.unlock_level:
        raise ValueError(f"tank requires level {tank.unlock_level}")
    return quote_purchase(tank.cost, wallet)


def purchase_tank(state: AquariumState, tank: AquariumTankSpec) -> AquariumState:
    if tank.id in state.owned_tanks:
        raise ValueError("tank already owned")
    tanks = dict(state.tanks)
    tanks[tank.id] = AquariumTankState(tank.id)
    return replace(state, tanks=tanks, owned_tanks=state.owned_tanks | {tank.id})


def purchase_decoration(state: AquariumState, decoration: DecorationSpec, *, quantity: int = 1) -> AquariumState:
    inventory = dict(state.owned_decorations)
    inventory[decoration.id] = inventory.get(decoration.id, 0) + count(quantity, "purchase quantity", positive=True)
    return replace(state, owned_decorations=inventory)


def add_fish(state: AquariumState, tank: AquariumTankSpec, fish: DisplayFish) -> FishTransferPlan:
    if tank.id not in state.owned_tanks or tank.id not in state.tanks:
        raise ValueError("tank not owned or missing")
    current = state.tanks[tank.id]
    if len(current.fish) >= tank.capacity:
        raise ValueError("tank is at capacity")
    if any(fish.id == existing.id for other in state.tanks.values() for existing in other.fish):
        raise ValueError("fish already displayed")
    tanks = dict(state.tanks)
    tanks[tank.id] = replace(current, fish=(*current.fish, fish))
    next_state = replace(state, tanks=tanks, total_fish_displayed=state.total_fish_displayed + 1)
    return FishTransferPlan(next_state, fish.id, tank.id)


def remove_fish(state: AquariumState, *, fish_id: str) -> FishTransferPlan:
    target = text(fish_id, "fish id")
    for tank_id, tank in state.tanks.items():
        if any(item.id == target for item in tank.fish):
            tanks = dict(state.tanks)
            tanks[tank_id] = replace(tank, fish=tuple(item for item in tank.fish if item.id != target))
            next_state = replace(state, tanks=tanks, total_fish_displayed=state.total_fish_displayed - 1)
            return FishTransferPlan(next_state, target, tank_id)
    raise ValueError("fish not found")


def place_decoration(state: AquariumState, tank: AquariumTankSpec, decoration: DecorationSpec, *, position: AquariumPosition, now: datetime, identity: Callable[[], str]) -> DecorationPlacementPlan:
    if tank.id not in state.owned_tanks or tank.id not in state.tanks:
        raise ValueError("tank not owned or missing")
    current = state.tanks[tank.id]
    if len(current.decorations) >= tank.decorations_allowed:
        raise ValueError("decoration limit reached")
    inventory = dict(state.owned_decorations)
    if inventory.get(decoration.id, 0) < 1:
        raise ValueError("decoration not owned")
    if not callable(identity):
        raise TypeError("identity must be callable")
    placed = PlacedDecoration(text(identity(), "decoration identity"), decoration.id, decoration.name, position, aware(now, "now"))
    if any(item.id == placed.id for item in current.decorations):
        raise ValueError("decoration identity already exists")
    inventory[decoration.id] -= 1
    tanks = dict(state.tanks)
    tanks[tank.id] = replace(current, decorations=(*current.decorations, placed))
    return DecorationPlacementPlan(replace(state, tanks=tanks, owned_decorations=inventory), placed)


def set_theme(state: AquariumState, *, tank_id: str, theme_id: str, allowed_themes: Iterable[str]) -> AquariumState:
    tank_key, theme = text(tank_id, "tank id"), text(theme_id, "theme id")
    if tank_key not in state.owned_tanks or tank_key not in state.tanks:
        raise ValueError("tank not owned or missing")
    if isinstance(allowed_themes, (str, bytes)):
        raise TypeError("allowed_themes must be an iterable of theme ids")
    allowed = {text(value, "allowed theme") for value in allowed_themes}
    if theme not in allowed:
        raise ValueError("theme not available")
    tanks = dict(state.tanks)
    tanks[tank_key] = replace(tanks[tank_key], theme=theme)
    return replace(state, tanks=tanks)

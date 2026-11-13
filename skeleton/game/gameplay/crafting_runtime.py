"""Offline source-bound crafting and finite inventory transactions (FLGB-13).

This is a deterministic game rule engine, not a payments or ownership system.
Each craft consumes all ingredients and funds atomically before yielding output.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Sequence

from .flgb_gameplay_runtime import GameplayContractError, EconomyRule, req_id, req_digest

MAX_RECIPES = 4096
MAX_ITEMS = 4096
MAX_EVENTS = 10000
MAX_STACK = 1_000_000_000
MAX_BATCH = 100
VERSION = 1


def _id(value: str, name: str) -> str:
    req_id(value, name)
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise GameplayContractError("invalid control character in " + name)
    return value


def _int(value: object, minimum: int = 0, maximum: int = MAX_STACK) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise GameplayContractError("invalid bounded quantity")
    return value


def _digest(value: object) -> str:
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, OverflowError) as exc:
        raise GameplayContractError("non-canonical crafting record") from exc
    return sha256(data).hexdigest()


def _stacks(values: Sequence[tuple[str, int]], *, allow_empty: bool = True) -> tuple[tuple[str, int], ...]:
    if len(values) > MAX_ITEMS or (not values and not allow_empty):
        raise GameplayContractError("inventory stack budget exceeded")
    checked = []
    for pair in values:
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise GameplayContractError("invalid item stack")
        item, count = pair
        checked.append((_id(item, "item_id"), _int(count, 1)))
    if len({name for name, _ in checked}) != len(checked):
        raise GameplayContractError("duplicate item stack")
    return tuple(sorted(checked))


def _flags(flags: Sequence[str]) -> tuple[str, ...]:
    if len(flags) > MAX_ITEMS:
        raise GameplayContractError("flag budget exceeded")
    checked = tuple(sorted(_id(flag, "flag") for flag in flags))
    if len(set(checked)) != len(checked):
        raise GameplayContractError("duplicate flag")
    return checked


@dataclass(frozen=True)
class CraftRecipe:
    recipe_id: str
    consumes: tuple[tuple[str, int], ...]
    produces: tuple[tuple[str, int], ...]
    currency_cost: int = 0
    requires: tuple[str, ...] = ()
    grants: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _id(self.recipe_id, "recipe_id")
        object.__setattr__(self, "consumes", _stacks(self.consumes, allow_empty=False))
        object.__setattr__(self, "produces", _stacks(self.produces, allow_empty=False))
        object.__setattr__(self, "requires", _flags(self.requires))
        object.__setattr__(self, "grants", _flags(self.grants))
        _int(self.currency_cost)

    def record(self) -> dict[str, object]:
        return {
            "recipe_id": self.recipe_id,
            "consumes": [list(pair) for pair in self.consumes],
            "produces": [list(pair) for pair in self.produces],
            "currency_cost": self.currency_cost,
            "requires": list(self.requires),
            "grants": list(self.grants),
        }


class CraftPlan:
    def __init__(self, world_id: str, recipes: Sequence[CraftRecipe],
                 initial_inventory: Sequence[tuple[str, int]], initial_currency: int = 0,
                 initial_flags: Sequence[str] = ()) -> None:
        self.world_id = _id(world_id, "world_id")
        if not recipes or len(recipes) > MAX_RECIPES or any(not isinstance(r, CraftRecipe) for r in recipes):
            raise GameplayContractError("invalid recipe catalog")
        if len({recipe.recipe_id for recipe in recipes}) != len(recipes):
            raise GameplayContractError("duplicate recipe")
        self.recipes = tuple(sorted(recipes, key=lambda r: r.recipe_id))
        self.by_id = {recipe.recipe_id: recipe for recipe in self.recipes}
        self.initial_inventory = _stacks(initial_inventory)
        self.initial_currency = _int(initial_currency)
        self.initial_flags = _flags(initial_flags)
        self.digest = _digest(self.record())

    def record(self) -> dict[str, object]:
        return {
            "schema_version": VERSION, "world_id": self.world_id,
            "recipes": [recipe.record() for recipe in self.recipes],
            "initial_inventory": [list(pair) for pair in self.initial_inventory],
            "initial_currency": self.initial_currency,
            "initial_flags": list(self.initial_flags),
        }

    @classmethod
    def parse(cls, record: object) -> "CraftPlan":
        if not isinstance(record, dict) or set(record) != {
            "schema_version", "world_id", "recipes", "initial_inventory",
            "initial_currency", "initial_flags",
        } or type(record["schema_version"]) is not int or record["schema_version"] != VERSION:
            raise GameplayContractError("unsupported crafting plan")
        raw_recipes = record["recipes"]
        if not isinstance(raw_recipes, list) or not 1 <= len(raw_recipes) <= MAX_RECIPES:
            raise GameplayContractError("invalid recipe list")
        recipes = []
        for raw in raw_recipes:
            if not isinstance(raw, dict) or set(raw) != {
                "recipe_id", "consumes", "produces", "currency_cost", "requires", "grants",
            }:
                raise GameplayContractError("invalid recipe record")
            if not all(
                isinstance(raw[name], list)
                for name in ("consumes", "produces", "requires", "grants")
            ):
                raise GameplayContractError("invalid recipe collections")
            recipes.append(CraftRecipe(
                raw["recipe_id"], tuple(raw["consumes"]), tuple(raw["produces"]),
                raw["currency_cost"], tuple(raw["requires"]), tuple(raw["grants"]),
            ))
        if not isinstance(record["initial_inventory"], list) or not isinstance(record["initial_flags"], list):
            raise GameplayContractError("invalid starting state")
        return cls(record["world_id"], recipes, record["initial_inventory"],
                   record["initial_currency"], record["initial_flags"])


@dataclass(frozen=True)
class CraftAction:
    sequence: int
    recipe_id: str
    batches: int = 1

    def __post_init__(self) -> None:
        _int(self.sequence, 0, MAX_EVENTS - 1)
        _id(self.recipe_id, "recipe_id")
        _int(self.batches, 1, MAX_BATCH)

    def record(self) -> dict[str, object]:
        return {"sequence": self.sequence, "recipe_id": self.recipe_id, "batches": self.batches}


@dataclass(frozen=True)
class CraftState:
    world_id: str
    plan_digest: str
    inventory: tuple[tuple[str, int], ...]
    currency: int
    flags: tuple[str, ...]
    actions: tuple[CraftAction, ...] = ()

    def __post_init__(self) -> None:
        _id(self.world_id, "world_id")
        req_digest(self.plan_digest, "plan_digest")
        if _stacks(self.inventory) != self.inventory or _flags(self.flags) != self.flags:
            raise GameplayContractError("non-canonical crafting state")
        _int(self.currency)
        if len(self.actions) > MAX_EVENTS:
            raise GameplayContractError("craft action budget exceeded")
        for i, action in enumerate(self.actions):
            if not isinstance(action, CraftAction) or action.sequence != i:
                raise GameplayContractError("non-canonical craft event log")

    def state_record(self) -> dict[str, object]:
        return {
            "world_id": self.world_id, "plan_digest": self.plan_digest,
            "inventory": [list(pair) for pair in self.inventory],
            "currency": self.currency, "flags": list(self.flags),
        }

    @property
    def digest(self) -> str:
        return _digest(self.state_record())

    def save_record(self) -> dict[str, object]:
        return {
            "schema_version": VERSION, "plan_digest": self.plan_digest,
            "actions": [action.record() for action in self.actions],
            "state": self.state_record(), "state_digest": self.digest,
        }


class CraftEngine:
    def __init__(self, plan: CraftPlan) -> None:
        if not isinstance(plan, CraftPlan):
            raise GameplayContractError("invalid crafting plan")
        self.plan = plan

    def start(self) -> CraftState:
        return CraftState(
            self.plan.world_id, self.plan.digest, self.plan.initial_inventory,
            self.plan.initial_currency, self.plan.initial_flags,
        )

    def _apply_verified(self, state: CraftState, action: CraftAction) -> CraftState:
        if state.world_id != self.plan.world_id or state.plan_digest != self.plan.digest:
            raise GameplayContractError("crafting plan identity mismatch")
        if len(state.actions) >= MAX_EVENTS or action.sequence != len(state.actions):
            raise GameplayContractError("crafting action sequence/budget mismatch")
        recipe = self.plan.by_id.get(action.recipe_id)
        if recipe is None:
            raise GameplayContractError("unknown crafting recipe")
        if not set(recipe.requires).issubset(state.flags):
            raise GameplayContractError("recipe prerequisites not unlocked")
        items = dict(state.inventory)
        for item, amount in recipe.consumes:
            total = amount * action.batches
            if items.get(item, 0) < total:
                raise GameplayContractError("insufficient owned ingredients")
            items[item] -= total
            if items[item] == 0:
                del items[item]
        fee = recipe.currency_cost * action.batches
        # Canonical EconomyRule validates a finite, non-negative currency domain.
        bounds = EconomyRule("game_coins", 0, MAX_STACK, MAX_STACK)
        next_currency, _ = bounds.transfer(state.currency, 0, fee)
        for item, amount in recipe.produces:
            total = items.get(item, 0) + amount * action.batches
            if total > MAX_STACK:
                raise GameplayContractError("crafted stack overflow")
            items[item] = total
        if len(items) > MAX_ITEMS:
            raise GameplayContractError("crafted inventory capacity exceeded")
        flags = _flags(tuple(state.flags) + tuple(
            flag for flag in recipe.grants if flag not in state.flags
        ))
        return CraftState(
            state.world_id, state.plan_digest, tuple(sorted(items.items())),
            next_currency, flags, state.actions + (action,),
        )

    def apply(self, state: CraftState, action: CraftAction) -> CraftState:
        if self.replay(state.actions) != state:
            raise GameplayContractError("unverified crafting event history")
        return self._apply_verified(state, action)

    def replay(self, actions: Sequence[CraftAction]) -> CraftState:
        if len(actions) > MAX_EVENTS:
            raise GameplayContractError("craft action budget exceeded")
        state = self.start()
        for action in actions:
            state = self._apply_verified(state, action)
        return state

    def restore(self, record: object) -> CraftState:
        if not isinstance(record, dict) or set(record) != {
            "schema_version", "plan_digest", "actions", "state", "state_digest",
        } or type(record["schema_version"]) is not int or record["schema_version"] != VERSION:
            raise GameplayContractError("invalid crafting save")
        if record["plan_digest"] != self.plan.digest:
            raise GameplayContractError("save source identity mismatch")
        actions = record["actions"]
        if not isinstance(actions, list) or len(actions) > MAX_EVENTS:
            raise GameplayContractError("invalid crafting action list")
        checked = []
        for action in actions:
            if not isinstance(action, dict) or set(action) != {"sequence", "recipe_id", "batches"}:
                raise GameplayContractError("invalid crafting action")
            checked.append(CraftAction(**action))
        state = self.replay(checked)
        if record["state"] != state.state_record() or record["state_digest"] != state.digest:
            raise GameplayContractError("crafting save tampered")
        return state

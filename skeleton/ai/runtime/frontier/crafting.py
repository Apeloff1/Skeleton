"""Pure crafting/workshop policy promoted from shared Lorebuffa/Openworld lineage.

Both source repositories carry the identical ``backend/crafting_routes.py`` blob
``9a9b159588605b8658b8d6043f62622c401dd8ba``. Source recipe/material catalogs,
FastAPI routes, MongoDB clients, wallet/inventory mutations and reward storage
remain source-owned. This module promotes only portable recipe normalization,
material checks, timed jobs, cancellation refunds, speed-up quotes, slot policy,
and crafting XP progression.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence


def _normalized_text(value: object, field_name: str) -> str:
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


def _aware(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _inventory(values: Mapping[str, int], field_name: str) -> dict[str, int]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    normalized: dict[str, int] = {}
    for raw_item, raw_quantity in values.items():
        item = _normalized_text(raw_item, f"{field_name} item")
        if item in normalized:
            raise ValueError(f"duplicate {field_name} item: {item}")
        normalized[item] = _nonnegative_int(
            raw_quantity, f"{field_name} quantity for {item}"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class CraftIngredient:
    item: str
    quantity: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "item", _normalized_text(self.item, "craft ingredient item"))
        object.__setattr__(
            self,
            "quantity",
            _positive_int(self.quantity, "craft ingredient quantity"),
        )


@dataclass(frozen=True, slots=True)
class CraftOutput:
    item: str
    quantity: int
    effect: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "item", _normalized_text(self.item, "craft output item"))
        object.__setattr__(
            self, "quantity", _positive_int(self.quantity, "craft output quantity")
        )
        if not isinstance(self.effect, Mapping):
            raise TypeError("craft output effect must be a mapping")
        object.__setattr__(self, "effect", dict(self.effect))


@dataclass(frozen=True, slots=True)
class CraftingRecipe:
    id: str
    name: str
    category: str
    ingredients: tuple[CraftIngredient, ...]
    output: CraftOutput
    craft_time_seconds: int
    xp_reward: int
    unlock_level: int
    description: str = ""
    icon: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _normalized_text(self.id, "craft recipe id"))
        object.__setattr__(self, "name", _normalized_text(self.name, "craft recipe name"))
        object.__setattr__(
            self,
            "category",
            _normalized_text(self.category, "craft recipe category").lower(),
        )
        if not self.ingredients:
            raise ValueError("craft recipe must have at least one ingredient")
        seen: set[str] = set()
        for ingredient in self.ingredients:
            if not isinstance(ingredient, CraftIngredient):
                raise TypeError("craft recipe ingredients must be CraftIngredient values")
            if ingredient.item in seen:
                raise ValueError(f"duplicate craft ingredient: {ingredient.item}")
            seen.add(ingredient.item)
        if not isinstance(self.output, CraftOutput):
            raise TypeError("craft recipe output must be CraftOutput")
        object.__setattr__(
            self,
            "craft_time_seconds",
            _positive_int(self.craft_time_seconds, "craft recipe craft_time_seconds"),
        )
        object.__setattr__(
            self, "xp_reward", _nonnegative_int(self.xp_reward, "craft recipe xp_reward")
        )
        object.__setattr__(
            self,
            "unlock_level",
            _positive_int(self.unlock_level, "craft recipe unlock_level"),
        )
        if not isinstance(self.metadata, Mapping):
            raise TypeError("craft recipe metadata must be a mapping")
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class CraftJob:
    recipe_id: str
    recipe_name: str
    started_at: datetime
    complete_at: datetime
    status: str
    output: CraftOutput
    xp_reward: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "recipe_id", _normalized_text(self.recipe_id, "craft job recipe_id")
        )
        object.__setattr__(
            self, "recipe_name", _normalized_text(self.recipe_name, "craft job recipe_name")
        )
        started = _aware(self.started_at, "craft job started_at")
        complete = _aware(self.complete_at, "craft job complete_at")
        if complete < started:
            raise ValueError("craft job complete_at must not precede started_at")
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "complete_at", complete)
        status = _normalized_text(self.status, "craft job status").lower()
        if status not in {"crafting", "complete"}:
            raise ValueError(f"unsupported craft job status: {status}")
        object.__setattr__(self, "status", status)
        if not isinstance(self.output, CraftOutput):
            raise TypeError("craft job output must be CraftOutput")
        object.__setattr__(
            self, "xp_reward", _nonnegative_int(self.xp_reward, "craft job xp_reward")
        )


@dataclass(frozen=True, slots=True)
class WorkshopState:
    crafting_slots: tuple[CraftJob | None, ...] = (None, None)
    max_slots: int = 2
    total_crafted: int = 0
    crafting_xp: int = 0
    crafting_level: int = 1
    unlocked_recipes: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        maximum = _positive_int(self.max_slots, "workshop max_slots")
        if len(self.crafting_slots) != maximum:
            raise ValueError("workshop crafting_slots length must equal max_slots")
        normalized_slots: list[CraftJob | None] = []
        for slot in self.crafting_slots:
            if slot is not None and not isinstance(slot, CraftJob):
                raise TypeError("workshop slots must contain CraftJob or None")
            normalized_slots.append(slot)
        unlocked: set[str] = set()
        for recipe_id in self.unlocked_recipes:
            normalized = _normalized_text(recipe_id, "workshop unlocked recipe id")
            if normalized in unlocked:
                raise ValueError(f"duplicate unlocked recipe id: {normalized}")
            unlocked.add(normalized)
        object.__setattr__(self, "crafting_slots", tuple(normalized_slots))
        object.__setattr__(self, "max_slots", maximum)
        object.__setattr__(
            self,
            "total_crafted",
            _nonnegative_int(self.total_crafted, "workshop total_crafted"),
        )
        object.__setattr__(
            self, "crafting_xp", _nonnegative_int(self.crafting_xp, "workshop crafting_xp")
        )
        object.__setattr__(
            self,
            "crafting_level",
            _positive_int(self.crafting_level, "workshop crafting_level"),
        )
        object.__setattr__(self, "unlocked_recipes", frozenset(unlocked))


@dataclass(frozen=True, slots=True)
class CraftStartPlan:
    workshop: WorkshopState
    materials: Mapping[str, int]
    job: CraftJob
    consumed_materials: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class CraftCollectPlan:
    workshop: WorkshopState
    output: CraftOutput
    xp_earned: int
    levels_gained: int


@dataclass(frozen=True, slots=True)
class CraftCancelPlan:
    workshop: WorkshopState
    returned_materials: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class SlotUnlockPlan:
    workshop: WorkshopState
    gem_cost: int


def recipe_from_record(record: Mapping[str, Any]) -> CraftingRecipe:
    if not isinstance(record, Mapping):
        raise TypeError("craft recipe record must be a mapping")

    raw_ingredients = record.get("ingredients")
    if not isinstance(raw_ingredients, Sequence) or isinstance(
        raw_ingredients, (str, bytes)
    ):
        raise TypeError("craft recipe ingredients must be a sequence")
    ingredients: list[CraftIngredient] = []
    for raw in raw_ingredients:
        if not isinstance(raw, Mapping):
            raise TypeError("craft ingredient record must be a mapping")
        ingredients.append(
            CraftIngredient(
                item=_normalized_text(raw.get("item"), "craft ingredient item"),
                quantity=_positive_int(
                    raw.get("quantity"), "craft ingredient quantity"
                ),
            )
        )

    raw_output = record.get("output")
    if not isinstance(raw_output, Mapping):
        raise TypeError("craft recipe output must be a mapping")
    effect = raw_output.get("effect", {})
    if not isinstance(effect, Mapping):
        raise TypeError("craft output effect must be a mapping")

    consumed = {
        "id",
        "name",
        "category",
        "description",
        "ingredients",
        "output",
        "craft_time_seconds",
        "xp_reward",
        "unlock_level",
        "icon",
    }
    return CraftingRecipe(
        id=_normalized_text(record.get("id"), "craft recipe id"),
        name=_normalized_text(record.get("name"), "craft recipe name"),
        category=_normalized_text(record.get("category"), "craft recipe category"),
        description=str(record.get("description") or "").strip(),
        ingredients=tuple(ingredients),
        output=CraftOutput(
            item=_normalized_text(raw_output.get("item"), "craft output item"),
            quantity=_positive_int(raw_output.get("quantity"), "craft output quantity"),
            effect=dict(effect),
        ),
        craft_time_seconds=_positive_int(
            record.get("craft_time_seconds"), "craft recipe craft_time_seconds"
        ),
        xp_reward=_nonnegative_int(record.get("xp_reward", 0), "craft recipe xp_reward"),
        unlock_level=_positive_int(
            record.get("unlock_level", 1), "craft recipe unlock_level"
        ),
        icon=str(record.get("icon") or "").strip(),
        metadata={key: value for key, value in record.items() if key not in consumed},
    )


def recipe_is_unlocked(
    recipe: CraftingRecipe,
    *,
    user_level: int,
    unlocked_recipes: Sequence[str] | frozenset[str] = (),
) -> bool:
    level = _positive_int(user_level, "craft user_level")
    explicit = {
        _normalized_text(item, "craft unlocked recipe id") for item in unlocked_recipes
    }
    return recipe.id in explicit or level >= recipe.unlock_level


def missing_materials(
    recipe: CraftingRecipe,
    materials: Mapping[str, int],
) -> Mapping[str, int]:
    inventory = _inventory(materials, "craft materials")
    missing: dict[str, int] = {}
    for ingredient in recipe.ingredients:
        shortfall = ingredient.quantity - inventory.get(ingredient.item, 0)
        if shortfall > 0:
            missing[ingredient.item] = shortfall
    return missing


def can_craft(
    recipe: CraftingRecipe,
    materials: Mapping[str, int],
    *,
    user_level: int,
    unlocked_recipes: Sequence[str] | frozenset[str] = (),
) -> bool:
    return recipe_is_unlocked(
        recipe,
        user_level=user_level,
        unlocked_recipes=unlocked_recipes,
    ) and not missing_materials(recipe, materials)


def refresh_workshop(
    workshop: WorkshopState,
    *,
    now: datetime,
) -> WorkshopState:
    current_time = _aware(now, "craft now")
    slots: list[CraftJob | None] = []
    for job in workshop.crafting_slots:
        if job is not None and job.status == "crafting" and current_time >= job.complete_at:
            job = replace(job, status="complete")
        slots.append(job)
    return replace(workshop, crafting_slots=tuple(slots))


def start_craft(
    workshop: WorkshopState,
    recipe: CraftingRecipe,
    materials: Mapping[str, int],
    *,
    slot: int,
    user_level: int,
    now: datetime,
) -> CraftStartPlan:
    if isinstance(slot, bool) or not isinstance(slot, int):
        raise TypeError("craft slot must be an integer")
    if slot < 0 or slot >= workshop.max_slots:
        raise ValueError("invalid crafting slot")
    current_time = _aware(now, "craft now")
    prepared = refresh_workshop(workshop, now=current_time)
    if prepared.crafting_slots[slot] is not None:
        raise ValueError("crafting slot is occupied")
    if not recipe_is_unlocked(
        recipe,
        user_level=user_level,
        unlocked_recipes=prepared.unlocked_recipes,
    ):
        raise ValueError(f"recipe requires level {recipe.unlock_level}")

    inventory = _inventory(materials, "craft materials")
    missing = missing_materials(recipe, inventory)
    if missing:
        detail = ", ".join(f"{item}:{quantity}" for item, quantity in sorted(missing.items()))
        raise ValueError(f"not enough crafting materials: {detail}")

    consumed = {ingredient.item: ingredient.quantity for ingredient in recipe.ingredients}
    remaining = dict(inventory)
    for item, quantity in consumed.items():
        remaining[item] = remaining.get(item, 0) - quantity

    job = CraftJob(
        recipe_id=recipe.id,
        recipe_name=recipe.name,
        started_at=current_time,
        complete_at=current_time + timedelta(seconds=recipe.craft_time_seconds),
        status="crafting",
        output=recipe.output,
        xp_reward=recipe.xp_reward,
    )
    slots = list(prepared.crafting_slots)
    slots[slot] = job
    return CraftStartPlan(
        workshop=replace(prepared, crafting_slots=tuple(slots)),
        materials=remaining,
        job=job,
        consumed_materials=consumed,
    )


def crafting_xp_threshold(level: int) -> int:
    return _positive_int(level, "crafting level") * 100


def _apply_crafting_xp(level: int, xp: int) -> tuple[int, int, int]:
    current_level = _positive_int(level, "crafting level")
    current_xp = _nonnegative_int(xp, "crafting xp")
    gained = 0
    while current_xp >= crafting_xp_threshold(current_level):
        current_xp -= crafting_xp_threshold(current_level)
        current_level += 1
        gained += 1
    return current_level, current_xp, gained


def collect_craft(
    workshop: WorkshopState,
    *,
    slot: int,
    now: datetime,
) -> CraftCollectPlan:
    if isinstance(slot, bool) or not isinstance(slot, int):
        raise TypeError("craft slot must be an integer")
    if slot < 0 or slot >= workshop.max_slots:
        raise ValueError("invalid crafting slot")
    prepared = refresh_workshop(workshop, now=now)
    job = prepared.crafting_slots[slot]
    if job is None:
        raise ValueError("no craft in this slot")
    if job.status != "complete":
        raise ValueError("craft not complete yet")

    level, xp, levels_gained = _apply_crafting_xp(
        prepared.crafting_level,
        prepared.crafting_xp + job.xp_reward,
    )
    slots = list(prepared.crafting_slots)
    slots[slot] = None
    updated = replace(
        prepared,
        crafting_slots=tuple(slots),
        total_crafted=prepared.total_crafted + 1,
        crafting_xp=xp,
        crafting_level=level,
    )
    return CraftCollectPlan(
        workshop=updated,
        output=job.output,
        xp_earned=job.xp_reward,
        levels_gained=levels_gained,
    )


def speed_up_cost(job: CraftJob, *, now: datetime) -> int:
    current_time = _aware(now, "craft now")
    if job.status == "complete" or current_time >= job.complete_at:
        return 0
    remaining_seconds = (job.complete_at - current_time).total_seconds()
    return max(1, int(remaining_seconds / 60))


def speed_up_craft(
    workshop: WorkshopState,
    *,
    slot: int,
    now: datetime,
) -> WorkshopState:
    if isinstance(slot, bool) or not isinstance(slot, int):
        raise TypeError("craft slot must be an integer")
    if slot < 0 or slot >= workshop.max_slots:
        raise ValueError("invalid crafting slot")
    current_time = _aware(now, "craft now")
    prepared = refresh_workshop(workshop, now=current_time)
    job = prepared.crafting_slots[slot]
    if job is None or job.status == "complete":
        raise ValueError("no active craft to speed up")
    slots = list(prepared.crafting_slots)
    slots[slot] = replace(job, status="complete", complete_at=current_time)
    return replace(prepared, crafting_slots=tuple(slots))


def cancel_refund(recipe: CraftingRecipe) -> Mapping[str, int]:
    return {
        ingredient.item: ingredient.quantity // 2
        for ingredient in recipe.ingredients
        if ingredient.quantity // 2 > 0
    }


def cancel_craft(
    workshop: WorkshopState,
    recipe: CraftingRecipe,
    *,
    slot: int,
    now: datetime,
) -> CraftCancelPlan:
    if isinstance(slot, bool) or not isinstance(slot, int):
        raise TypeError("craft slot must be an integer")
    if slot < 0 or slot >= workshop.max_slots:
        raise ValueError("invalid crafting slot")
    prepared = refresh_workshop(workshop, now=now)
    job = prepared.crafting_slots[slot]
    if job is None:
        raise ValueError("no craft in this slot")
    if job.status == "complete":
        raise ValueError("cannot cancel completed craft")
    if job.recipe_id != recipe.id:
        raise ValueError("craft job recipe does not match cancellation recipe")

    slots = list(prepared.crafting_slots)
    slots[slot] = None
    return CraftCancelPlan(
        workshop=replace(prepared, crafting_slots=tuple(slots)),
        returned_materials=cancel_refund(recipe),
    )


def unlock_slot_cost(max_slots: int) -> int:
    return 100 * _positive_int(max_slots, "workshop max_slots")


def unlock_crafting_slot(
    workshop: WorkshopState,
    *,
    max_possible_slots: int = 5,
) -> SlotUnlockPlan:
    maximum = _positive_int(max_possible_slots, "max_possible_slots")
    if workshop.max_slots >= maximum:
        raise ValueError("maximum crafting slots reached")
    cost = unlock_slot_cost(workshop.max_slots)
    slots = (*workshop.crafting_slots, None)
    return SlotUnlockPlan(
        workshop=replace(
            workshop,
            crafting_slots=slots,
            max_slots=workshop.max_slots + 1,
        ),
        gem_cost=cost,
    )

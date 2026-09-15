"""Pure cooking/kitchen policy promoted from Lorebuffa/Openworld lineage.

The source repositories carry semantically equivalent ``backend/cooking_routes.py``
implementations with a one-character presentation-only divergence in one error
message. FastAPI, MongoDB, user-wallet mutation, tacklebox persistence and recipe
catalog ownership remain source-owned. This module promotes only portable policy:
recipe normalization, unlock checks, typed ingredient allocation, timed kitchen
slots, collection rewards and expiring cooking buffs.

Cooking jobs bind the executable recipe semantics at start time. Collection
revalidates that digest so a same-id recipe cannot be substituted later to alter
rewards or buffs.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Mapping, Sequence

from skeleton.frontier.contracts import stable_content_digest


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


def _integer_map(values: Mapping[str, int], field_name: str) -> dict[str, int]:
    return _inventory(values, field_name)


def _effect_map(
    values: Mapping[str, Any], field_name: str
) -> dict[str, float | int | str | bool]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    normalized: dict[str, float | int | str | bool] = {}
    for raw_key, raw_value in values.items():
        key = _normalized_text(raw_key, f"{field_name} key")
        if key in normalized:
            raise ValueError(f"duplicate {field_name} key: {key}")
        if isinstance(raw_value, bool):
            normalized[key] = raw_value
        elif isinstance(raw_value, int):
            normalized[key] = raw_value
        elif isinstance(raw_value, float):
            if not math.isfinite(raw_value):
                raise ValueError(f"{field_name} value for {key} must be finite")
            normalized[key] = raw_value
        elif isinstance(raw_value, str):
            normalized[key] = _normalized_text(
                raw_value, f"{field_name} value for {key}"
            )
        else:
            raise TypeError(
                f"{field_name} value for {key} must be JSON-scalar compatible"
            )
    return normalized


def _sha256_hex(value: object, field_name: str) -> str:
    digest = _normalized_text(value, field_name)
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")
    return digest


@dataclass(frozen=True, slots=True)
class CookingIngredient:
    kind: str
    quantity: int
    item_id: str | None = None
    fish_ids: tuple[str, ...] = ()
    min_size: float = 0.0

    def __post_init__(self) -> None:
        kind = _normalized_text(self.kind, "cooking ingredient kind").lower()
        if kind not in {"item", "fish"}:
            raise ValueError(f"unsupported cooking ingredient kind: {kind}")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(
            self,
            "quantity",
            _positive_int(self.quantity, "cooking ingredient quantity"),
        )
        object.__setattr__(
            self,
            "min_size",
            _nonnegative_number(self.min_size, "cooking ingredient min_size"),
        )
        if kind == "item":
            if self.item_id is None:
                raise ValueError("item cooking ingredient requires item_id")
            object.__setattr__(
                self,
                "item_id",
                _normalized_text(self.item_id, "cooking ingredient item_id"),
            )
            if self.fish_ids:
                raise ValueError("item cooking ingredient must not define fish_ids")
            if self.min_size != 0.0:
                raise ValueError("item cooking ingredient must not define min_size")
            return
        if self.item_id is not None:
            raise ValueError("fish cooking ingredient must not define item_id")
        if not self.fish_ids:
            raise ValueError("fish cooking ingredient requires fish_ids")
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in self.fish_ids:
            fish_id = _normalized_text(raw, "cooking ingredient fish_id")
            if fish_id in seen:
                raise ValueError(f"duplicate cooking ingredient fish_id: {fish_id}")
            seen.add(fish_id)
            normalized.append(fish_id)
        object.__setattr__(self, "fish_ids", tuple(normalized))


@dataclass(frozen=True, slots=True)
class FishInventoryItem:
    id: str
    species: str
    size: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _normalized_text(self.id, "fish inventory id"))
        object.__setattr__(
            self,
            "species",
            _normalized_text(self.species, "fish inventory species"),
        )
        object.__setattr__(
            self, "size", _nonnegative_number(self.size, "fish inventory size")
        )


@dataclass(frozen=True, slots=True)
class CookingRecipe:
    id: str
    name: str
    category: str
    difficulty: int
    ingredients: tuple[CookingIngredient, ...]
    cooking_time_seconds: int
    required_station: str
    unlock_level: int
    rewards: Mapping[str, int] = field(default_factory=dict)
    stats_boost: Mapping[str, float | int | str | bool] = field(default_factory=dict)
    description: str = ""
    icon: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _normalized_text(self.id, "cooking recipe id"))
        object.__setattr__(
            self, "name", _normalized_text(self.name, "cooking recipe name")
        )
        object.__setattr__(
            self,
            "category",
            _normalized_text(self.category, "cooking recipe category").lower(),
        )
        object.__setattr__(
            self,
            "difficulty",
            _positive_int(self.difficulty, "cooking recipe difficulty"),
        )
        if not self.ingredients:
            raise ValueError("cooking recipe must have at least one ingredient")
        for ingredient in self.ingredients:
            if not isinstance(ingredient, CookingIngredient):
                raise TypeError(
                    "cooking recipe ingredients must be CookingIngredient values"
                )
        object.__setattr__(self, "ingredients", tuple(self.ingredients))
        object.__setattr__(
            self,
            "cooking_time_seconds",
            _positive_int(
                self.cooking_time_seconds, "cooking recipe cooking_time_seconds"
            ),
        )
        object.__setattr__(
            self,
            "required_station",
            _normalized_text(
                self.required_station, "cooking recipe required_station"
            ),
        )
        object.__setattr__(
            self,
            "unlock_level",
            _positive_int(self.unlock_level, "cooking recipe unlock_level"),
        )
        object.__setattr__(
            self, "rewards", _integer_map(self.rewards, "cooking rewards")
        )
        object.__setattr__(
            self,
            "stats_boost",
            _effect_map(self.stats_boost, "cooking stats_boost"),
        )
        if not isinstance(self.description, str):
            raise TypeError("cooking recipe description must be a string")
        if not isinstance(self.icon, str):
            raise TypeError("cooking recipe icon must be a string")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("cooking recipe metadata must be a mapping")
        object.__setattr__(self, "metadata", dict(self.metadata))


def cooking_recipe_digest(recipe: CookingRecipe) -> str:
    """Digest the executable semantics used by a cooking job and its claim."""

    if not isinstance(recipe, CookingRecipe):
        raise TypeError("recipe must be CookingRecipe")
    ingredients = [
        {
            "kind": ingredient.kind,
            "quantity": ingredient.quantity,
            "item_id": ingredient.item_id,
            "fish_ids": list(ingredient.fish_ids),
            "min_size": ingredient.min_size,
        }
        for ingredient in recipe.ingredients
    ]
    return stable_content_digest(
        {
            "id": recipe.id,
            "name": recipe.name,
            "category": recipe.category,
            "difficulty": recipe.difficulty,
            "ingredients": ingredients,
            "cooking_time_seconds": recipe.cooking_time_seconds,
            "required_station": recipe.required_station,
            "unlock_level": recipe.unlock_level,
            "rewards": dict(recipe.rewards),
            "stats_boost": dict(recipe.stats_boost),
        }
    )


@dataclass(frozen=True, slots=True)
class CookingJob:
    recipe_id: str
    recipe_name: str
    recipe_digest: str
    started_at: datetime
    complete_at: datetime
    status: str = "cooking"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "recipe_id", _normalized_text(self.recipe_id, "cooking job recipe_id")
        )
        object.__setattr__(
            self,
            "recipe_name",
            _normalized_text(self.recipe_name, "cooking job recipe_name"),
        )
        object.__setattr__(
            self,
            "recipe_digest",
            _sha256_hex(self.recipe_digest, "cooking job recipe_digest"),
        )
        started = _aware(self.started_at, "cooking job started_at")
        complete = _aware(self.complete_at, "cooking job complete_at")
        if complete < started:
            raise ValueError("cooking job complete_at must not precede started_at")
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "complete_at", complete)
        status = _normalized_text(self.status, "cooking job status").lower()
        if status not in {"cooking", "complete"}:
            raise ValueError(f"unsupported cooking job status: {status}")
        object.__setattr__(self, "status", status)


@dataclass(frozen=True, slots=True)
class ActiveCookingBuff:
    recipe_id: str
    name: str
    effects: Mapping[str, float | int | str | bool]
    expires_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "recipe_id",
            _normalized_text(self.recipe_id, "cooking buff recipe_id"),
        )
        object.__setattr__(
            self, "name", _normalized_text(self.name, "cooking buff name")
        )
        object.__setattr__(
            self, "effects", _effect_map(self.effects, "cooking buff effects")
        )
        object.__setattr__(
            self, "expires_at", _aware(self.expires_at, "cooking buff expires_at")
        )


@dataclass(frozen=True, slots=True)
class KitchenState:
    cooking_slots: tuple[CookingJob | None, ...] = (None, None)
    max_slots: int = 2
    ingredients: Mapping[str, int] = field(default_factory=dict)
    unlocked_recipes: frozenset[str] = frozenset({"grilled_bass", "fried_panfish"})
    cooking_level: int = 1
    cooking_xp: int = 0
    dishes_cooked: int = 0
    active_buffs: tuple[ActiveCookingBuff, ...] = ()

    def __post_init__(self) -> None:
        maximum = _positive_int(self.max_slots, "kitchen max_slots")
        if len(self.cooking_slots) != maximum:
            raise ValueError("kitchen cooking_slots length must equal max_slots")
        for slot in self.cooking_slots:
            if slot is not None and not isinstance(slot, CookingJob):
                raise TypeError("kitchen slots must contain CookingJob or None")
        object.__setattr__(self, "max_slots", maximum)
        object.__setattr__(self, "cooking_slots", tuple(self.cooking_slots))
        object.__setattr__(
            self, "ingredients", _inventory(self.ingredients, "kitchen ingredients")
        )
        if isinstance(self.unlocked_recipes, (str, bytes)) or not isinstance(
            self.unlocked_recipes, (Sequence, set, frozenset)
        ):
            raise TypeError("kitchen unlocked_recipes must be a collection of strings")
        normalized_unlocked: set[str] = set()
        for raw in self.unlocked_recipes:
            recipe_id = _normalized_text(raw, "kitchen unlocked recipe id")
            if recipe_id in normalized_unlocked:
                raise ValueError(f"duplicate unlocked cooking recipe id: {recipe_id}")
            normalized_unlocked.add(recipe_id)
        object.__setattr__(self, "unlocked_recipes", frozenset(normalized_unlocked))
        object.__setattr__(
            self,
            "cooking_level",
            _positive_int(self.cooking_level, "kitchen cooking_level"),
        )
        object.__setattr__(
            self,
            "cooking_xp",
            _nonnegative_int(self.cooking_xp, "kitchen cooking_xp"),
        )
        object.__setattr__(
            self,
            "dishes_cooked",
            _nonnegative_int(self.dishes_cooked, "kitchen dishes_cooked"),
        )
        for buff in self.active_buffs:
            if not isinstance(buff, ActiveCookingBuff):
                raise TypeError(
                    "kitchen active_buffs must contain ActiveCookingBuff values"
                )
        object.__setattr__(self, "active_buffs", tuple(self.active_buffs))


@dataclass(frozen=True, slots=True)
class CookingStartPlan:
    kitchen: KitchenState
    remaining_ingredients: Mapping[str, int]
    remaining_fish: tuple[FishInventoryItem, ...]
    consumed_ingredients: Mapping[str, int]
    consumed_fish_ids: tuple[str, ...]
    slot: int
    job: CookingJob


@dataclass(frozen=True, slots=True)
class CookingCollectPlan:
    kitchen: KitchenState
    recipe_id: str
    rewards: Mapping[str, int]
    buff: ActiveCookingBuff | None
    xp_earned: int


def recipe_from_record(record: Mapping[str, Any]) -> CookingRecipe:
    if not isinstance(record, Mapping):
        raise TypeError("cooking recipe record must be a mapping")
    raw_ingredients = record.get("ingredients")
    if not isinstance(raw_ingredients, Sequence) or isinstance(
        raw_ingredients, (str, bytes)
    ):
        raise TypeError("cooking recipe ingredients must be a sequence")

    ingredients: list[CookingIngredient] = []
    for raw in raw_ingredients:
        if not isinstance(raw, Mapping):
            raise TypeError("cooking ingredient record must be a mapping")
        kind = _normalized_text(raw.get("type"), "cooking ingredient type").lower()
        if kind == "item":
            ingredients.append(
                CookingIngredient(
                    kind="item",
                    item_id=_normalized_text(
                        raw.get("item_id"), "cooking ingredient item_id"
                    ),
                    quantity=_positive_int(
                        raw.get("quantity"), "cooking ingredient quantity"
                    ),
                )
            )
        elif kind == "fish":
            raw_fish_ids = raw.get("fish_ids")
            if not isinstance(raw_fish_ids, Sequence) or isinstance(
                raw_fish_ids, (str, bytes)
            ):
                raise TypeError("cooking fish_ids must be a sequence")
            ingredients.append(
                CookingIngredient(
                    kind="fish",
                    fish_ids=tuple(
                        _normalized_text(value, "cooking ingredient fish_id")
                        for value in raw_fish_ids
                    ),
                    quantity=_positive_int(
                        raw.get("quantity"), "cooking ingredient quantity"
                    ),
                    min_size=_nonnegative_number(
                        raw.get("min_size", 0), "cooking ingredient min_size"
                    ),
                )
            )
        else:
            raise ValueError(f"unsupported cooking ingredient type: {kind}")

    raw_rewards = record.get("rewards", {})
    if not isinstance(raw_rewards, Mapping):
        raise TypeError("cooking recipe rewards must be a mapping")
    raw_boost = record.get("stats_boost", {})
    if not isinstance(raw_boost, Mapping):
        raise TypeError("cooking recipe stats_boost must be a mapping")

    description = record.get("description", "")
    if description is None:
        description = ""
    if not isinstance(description, str):
        raise TypeError("cooking recipe description must be a string")
    icon = record.get("icon", "")
    if icon is None:
        icon = ""
    if not isinstance(icon, str):
        raise TypeError("cooking recipe icon must be a string")

    consumed = {
        "id",
        "name",
        "category",
        "difficulty",
        "description",
        "ingredients",
        "cooking_time_seconds",
        "required_station",
        "unlock_level",
        "rewards",
        "stats_boost",
        "icon",
    }
    return CookingRecipe(
        id=_normalized_text(record.get("id"), "cooking recipe id"),
        name=_normalized_text(record.get("name"), "cooking recipe name"),
        category=_normalized_text(record.get("category"), "cooking recipe category"),
        difficulty=_positive_int(
            record.get("difficulty"), "cooking recipe difficulty"
        ),
        description=description.strip(),
        ingredients=tuple(ingredients),
        cooking_time_seconds=_positive_int(
            record.get("cooking_time_seconds"),
            "cooking recipe cooking_time_seconds",
        ),
        required_station=_normalized_text(
            record.get("required_station"), "cooking recipe required_station"
        ),
        unlock_level=_positive_int(
            record.get("unlock_level", 1), "cooking recipe unlock_level"
        ),
        rewards={
            _normalized_text(key, "cooking reward key"): _nonnegative_int(
                value, f"cooking reward {key}"
            )
            for key, value in raw_rewards.items()
        },
        stats_boost=dict(raw_boost),
        icon=icon.strip(),
        metadata={key: value for key, value in record.items() if key not in consumed},
    )


def recipe_is_unlocked(
    recipe: CookingRecipe,
    *,
    user_level: int,
    unlocked_recipes: Sequence[str] | frozenset[str] = (),
) -> bool:
    if not isinstance(recipe, CookingRecipe):
        raise TypeError("recipe must be CookingRecipe")
    level = _positive_int(user_level, "cooking user_level")
    if isinstance(unlocked_recipes, (str, bytes)) or not isinstance(
        unlocked_recipes, (Sequence, set, frozenset)
    ):
        raise TypeError("unlocked_recipes must be a collection of strings")
    normalized = {
        _normalized_text(value, "unlocked cooking recipe id")
        for value in unlocked_recipes
    }
    return recipe.id in normalized or level >= recipe.unlock_level


def ingredient_purchase_cost(
    cost: Mapping[str, int], quantity: int
) -> Mapping[str, int]:
    normalized_cost = _integer_map(cost, "cooking ingredient cost")
    count = _positive_int(quantity, "cooking ingredient purchase quantity")
    return {currency: amount * count for currency, amount in normalized_cost.items()}


def refresh_kitchen(state: KitchenState, *, now: datetime) -> KitchenState:
    if not isinstance(state, KitchenState):
        raise TypeError("state must be KitchenState")
    current = _aware(now, "cooking now")
    slots: list[CookingJob | None] = []
    for slot in state.cooking_slots:
        if (
            slot is not None
            and slot.status == "cooking"
            and current >= slot.complete_at
        ):
            slot = replace(slot, status="complete")
        slots.append(slot)
    buffs = tuple(buff for buff in state.active_buffs if buff.expires_at > current)
    if tuple(slots) == state.cooking_slots and buffs == state.active_buffs:
        return state
    return replace(state, cooking_slots=tuple(slots), active_buffs=buffs)


def _allocate_fish(
    ingredients: Sequence[CookingIngredient],
    fish_inventory: Sequence[FishInventoryItem],
) -> tuple[tuple[str, ...], tuple[FishInventoryItem, ...]]:
    if isinstance(fish_inventory, (str, bytes)) or not isinstance(
        fish_inventory, Sequence
    ):
        raise TypeError("fish_inventory must be a sequence")

    seen_ids: set[str] = set()
    normalized_fish: list[FishInventoryItem] = []
    for fish in fish_inventory:
        if not isinstance(fish, FishInventoryItem):
            raise TypeError("fish_inventory must contain FishInventoryItem values")
        if fish.id in seen_ids:
            raise ValueError(f"duplicate fish inventory id: {fish.id}")
        seen_ids.add(fish.id)
        normalized_fish.append(fish)

    consumed: list[str] = []
    available = list(normalized_fish)
    for ingredient in ingredients:
        if ingredient.kind != "fish":
            continue
        selected: list[FishInventoryItem] = []
        for fish_id in ingredient.fish_ids:
            for fish in available:
                if fish.species != fish_id or fish.size < ingredient.min_size:
                    continue
                selected.append(fish)
                if len(selected) == ingredient.quantity:
                    break
            if len(selected) == ingredient.quantity:
                break
        if len(selected) != ingredient.quantity:
            accepted = ", ".join(ingredient.fish_ids)
            raise ValueError(
                "not enough eligible fish for cooking requirement "
                f"({accepted}); need {ingredient.quantity}"
            )
        selected_ids = {fish.id for fish in selected}
        consumed.extend(fish.id for fish in selected)
        available = [fish for fish in available if fish.id not in selected_ids]
    return tuple(consumed), tuple(available)


def start_cooking(
    state: KitchenState,
    recipe: CookingRecipe,
    *,
    user_level: int,
    fish_inventory: Sequence[FishInventoryItem],
    now: datetime,
) -> CookingStartPlan:
    if not isinstance(state, KitchenState):
        raise TypeError("state must be KitchenState")
    if not isinstance(recipe, CookingRecipe):
        raise TypeError("recipe must be CookingRecipe")
    current = _aware(now, "cooking now")
    state = refresh_kitchen(state, now=current)
    if not recipe_is_unlocked(
        recipe,
        user_level=user_level,
        unlocked_recipes=state.unlocked_recipes,
    ):
        raise ValueError(f"cooking recipe {recipe.id} is locked")
    try:
        slot_index = next(
            index for index, slot in enumerate(state.cooking_slots) if slot is None
        )
    except StopIteration as exc:
        raise ValueError("no empty cooking slots") from exc

    remaining_items = dict(state.ingredients)
    consumed_items: dict[str, int] = {}
    for ingredient in recipe.ingredients:
        if ingredient.kind != "item":
            continue
        assert ingredient.item_id is not None
        available = remaining_items.get(ingredient.item_id, 0)
        if available < ingredient.quantity:
            raise ValueError(f"not enough cooking ingredient: {ingredient.item_id}")
        remaining_items[ingredient.item_id] = available - ingredient.quantity
        consumed_items[ingredient.item_id] = (
            consumed_items.get(ingredient.item_id, 0) + ingredient.quantity
        )

    consumed_fish, remaining_fish = _allocate_fish(
        recipe.ingredients, fish_inventory
    )
    job = CookingJob(
        recipe_id=recipe.id,
        recipe_name=recipe.name,
        recipe_digest=cooking_recipe_digest(recipe),
        started_at=current,
        complete_at=current + timedelta(seconds=recipe.cooking_time_seconds),
        status="cooking",
    )
    slots = list(state.cooking_slots)
    slots[slot_index] = job
    next_state = replace(
        state, cooking_slots=tuple(slots), ingredients=remaining_items
    )
    return CookingStartPlan(
        kitchen=next_state,
        remaining_ingredients=remaining_items,
        remaining_fish=remaining_fish,
        consumed_ingredients=consumed_items,
        consumed_fish_ids=consumed_fish,
        slot=slot_index,
        job=job,
    )


def collect_dish(
    state: KitchenState,
    recipe: CookingRecipe,
    *,
    slot: int,
    now: datetime,
) -> CookingCollectPlan:
    if not isinstance(state, KitchenState):
        raise TypeError("state must be KitchenState")
    if not isinstance(recipe, CookingRecipe):
        raise TypeError("recipe must be CookingRecipe")
    current = _aware(now, "cooking now")
    state = refresh_kitchen(state, now=current)
    if isinstance(slot, bool) or not isinstance(slot, int):
        raise TypeError("cooking slot must be an integer")
    if slot < 0 or slot >= state.max_slots:
        raise ValueError("invalid cooking slot")
    job = state.cooking_slots[slot]
    if job is None or job.status != "complete":
        raise ValueError("dish is not ready")
    if job.recipe_id != recipe.id:
        raise ValueError("cooking recipe does not match completed job")
    if job.recipe_digest != cooking_recipe_digest(recipe):
        raise ValueError("cooking recipe semantics do not match completed job")

    buff: ActiveCookingBuff | None = None
    next_buffs = state.active_buffs
    if recipe.stats_boost:
        duration = recipe.stats_boost.get("duration_minutes")
        if duration is None:
            raise ValueError("cooking stats_boost requires duration_minutes")
        duration_minutes = _positive_int(duration, "cooking buff duration_minutes")
        effects = {
            key: value
            for key, value in recipe.stats_boost.items()
            if key != "duration_minutes"
        }
        if effects:
            buff = ActiveCookingBuff(
                recipe_id=recipe.id,
                name=recipe.name,
                effects=effects,
                expires_at=current + timedelta(minutes=duration_minutes),
            )
            next_buffs = (*next_buffs, buff)

    slots = list(state.cooking_slots)
    slots[slot] = None
    xp_earned = _nonnegative_int(
        recipe.rewards.get("xp", 0), "cooking xp reward"
    )
    next_state = replace(
        state,
        cooking_slots=tuple(slots),
        cooking_xp=state.cooking_xp + xp_earned,
        dishes_cooked=state.dishes_cooked + 1,
        active_buffs=tuple(next_buffs),
    )
    return CookingCollectPlan(
        kitchen=next_state,
        recipe_id=recipe.id,
        rewards=dict(recipe.rewards),
        buff=buff,
        xp_earned=xp_earned,
    )


def active_buffs(
    state: KitchenState, *, now: datetime
) -> tuple[ActiveCookingBuff, ...]:
    return refresh_kitchen(state, now=now).active_buffs

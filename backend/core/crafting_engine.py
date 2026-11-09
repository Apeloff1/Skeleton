"""Storage-neutral crafting engine mined from Openworld4.

Recipes, inventory mutation, level gates, timed jobs, cancellation and collection
live here without FastAPI or MongoDB coupling. The engine is deterministic when
provided an explicit clock and supports multiple concurrent workshop slots.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Callable
import uuid


@dataclass(frozen=True, slots=True)
class Ingredient:
    item: str
    quantity: int

    def __post_init__(self) -> None:
        if not self.item or self.quantity <= 0:
            raise ValueError("ingredient requires item and positive quantity")


@dataclass(frozen=True, slots=True)
class CraftOutput:
    item: str
    quantity: int
    effects: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.item or self.quantity <= 0:
            raise ValueError("output requires item and positive quantity")


@dataclass(frozen=True, slots=True)
class Recipe:
    id: str
    category: str
    ingredients: tuple[Ingredient, ...]
    output: CraftOutput
    craft_seconds: int
    xp_reward: int = 0
    unlock_level: int = 1

    def __post_init__(self) -> None:
        if not self.id or not self.category:
            raise ValueError("recipe id/category required")
        if self.craft_seconds < 0 or self.xp_reward < 0 or self.unlock_level < 1:
            raise ValueError("invalid recipe timing/xp/level")


@dataclass(slots=True)
class CraftJob:
    id: str
    recipe_id: str
    slot: int
    started_at: datetime
    completes_at: datetime
    collected: bool = False
    cancelled: bool = False

    def complete(self, now: datetime) -> bool:
        return not self.cancelled and now >= self.completes_at


class CraftingError(RuntimeError):
    pass


class Workshop:
    def __init__(self, recipes: tuple[Recipe, ...], *, slots: int = 2) -> None:
        if slots <= 0:
            raise ValueError("slots must be positive")
        self.recipes = {r.id: r for r in recipes}
        if len(self.recipes) != len(recipes):
            raise ValueError("recipe ids must be unique")
        self.slots = slots
        self.jobs: dict[int, CraftJob] = {}
        self.inventory: dict[str, int] = {}
        self.crafting_xp = 0
        self.total_crafted = 0

    @property
    def level(self) -> int:
        return 1 + self.crafting_xp // 100

    def add_item(self, item: str, quantity: int) -> None:
        if not item or quantity <= 0:
            raise ValueError("item and positive quantity required")
        self.inventory[item] = self.inventory.get(item, 0) + quantity

    def can_craft(self, recipe_id: str) -> tuple[bool, str]:
        recipe = self.recipes.get(recipe_id)
        if recipe is None:
            return False, "unknown recipe"
        if self.level < recipe.unlock_level:
            return False, "recipe level locked"
        for ingredient in recipe.ingredients:
            if self.inventory.get(ingredient.item, 0) < ingredient.quantity:
                return False, f"missing {ingredient.item}"
        return True, "ready"

    def start(self, recipe_id: str, *, slot: int, now: datetime | None = None) -> CraftJob:
        if slot < 0 or slot >= self.slots:
            raise CraftingError("invalid workshop slot")
        current = self.jobs.get(slot)
        if current and not current.collected and not current.cancelled:
            raise CraftingError("workshop slot occupied")
        ok, reason = self.can_craft(recipe_id)
        if not ok:
            raise CraftingError(reason)
        recipe = self.recipes[recipe_id]
        for ingredient in recipe.ingredients:
            remaining = self.inventory[ingredient.item] - ingredient.quantity
            if remaining:
                self.inventory[ingredient.item] = remaining
            else:
                self.inventory.pop(ingredient.item, None)
        stamp = now or datetime.now(UTC)
        job = CraftJob(
            id=uuid.uuid4().hex,
            recipe_id=recipe_id,
            slot=slot,
            started_at=stamp,
            completes_at=stamp + timedelta(seconds=recipe.craft_seconds),
        )
        self.jobs[slot] = job
        return job

    def cancel(self, slot: int) -> dict[str, int]:
        job = self.jobs.get(slot)
        if job is None or job.collected or job.cancelled:
            raise CraftingError("no cancellable job")
        recipe = self.recipes[job.recipe_id]
        refunded: dict[str, int] = {}
        for ingredient in recipe.ingredients:
            self.add_item(ingredient.item, ingredient.quantity)
            refunded[ingredient.item] = ingredient.quantity
        job.cancelled = True
        return refunded

    def collect(self, slot: int, *, now: datetime | None = None) -> CraftOutput:
        job = self.jobs.get(slot)
        if job is None or job.cancelled or job.collected:
            raise CraftingError("no collectible job")
        stamp = now or datetime.now(UTC)
        if not job.complete(stamp):
            raise CraftingError("craft is not complete")
        recipe = self.recipes[job.recipe_id]
        self.add_item(recipe.output.item, recipe.output.quantity)
        self.crafting_xp += recipe.xp_reward
        self.total_crafted += recipe.output.quantity
        job.collected = True
        return recipe.output

    def speed_up(self, slot: int, seconds: int) -> None:
        if seconds <= 0:
            raise ValueError("seconds must be positive")
        job = self.jobs.get(slot)
        if job is None or job.cancelled or job.collected:
            raise CraftingError("no active job")
        job.completes_at = max(job.started_at, job.completes_at - timedelta(seconds=seconds))

    def snapshot(self) -> dict[str, object]:
        return {
            "level": self.level,
            "crafting_xp": self.crafting_xp,
            "total_crafted": self.total_crafted,
            "inventory": dict(self.inventory),
            "jobs": {
                slot: {
                    "id": job.id,
                    "recipe_id": job.recipe_id,
                    "started_at": job.started_at.isoformat(),
                    "completes_at": job.completes_at.isoformat(),
                    "collected": job.collected,
                    "cancelled": job.cancelled,
                }
                for slot, job in self.jobs.items()
            },
        }

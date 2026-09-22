"""Cross-contract adapters for promoted crafting policy."""

from __future__ import annotations

from skeleton.frontier.crafting import CraftingRecipe
from skeleton.frontier.energy import EnergyBoosterSpec


def energy_booster_from_craft_output(recipe: CraftingRecipe) -> EnergyBoosterSpec:
    """Adapt one explicitly energy-shaped craft output to ``EnergyBoosterSpec``.

    The adapter is deliberately narrow: it never guesses how unrelated effect
    metadata (XP, luck, inventory capacity, etc.) should behave. Unsupported or
    mixed effect shapes fail closed instead of silently discarding semantics.
    ``CraftOutput.quantity`` remains an inventory concern; the returned booster
    describes the effect of consuming one crafted output item.
    """

    effect = dict(recipe.output.effect)
    if not effect:
        raise ValueError("craft output has no energy effect")

    keys = frozenset(effect)
    if keys == {"energy_restore"}:
        return EnergyBoosterSpec(
            id=recipe.output.item,
            name=recipe.name,
            energy_restore=effect["energy_restore"],
        )
    if keys == {"infinite_duration_minutes"}:
        return EnergyBoosterSpec(
            id=recipe.output.item,
            name=recipe.name,
            infinite_duration_minutes=effect["infinite_duration_minutes"],
        )
    if keys == {"regen_multiplier", "duration_minutes"}:
        return EnergyBoosterSpec(
            id=recipe.output.item,
            name=recipe.name,
            regen_multiplier=effect["regen_multiplier"],
            duration_minutes=effect["duration_minutes"],
        )

    raise ValueError("craft output effect is not a canonical energy booster shape")

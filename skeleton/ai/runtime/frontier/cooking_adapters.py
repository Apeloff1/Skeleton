"""Boundary adapters for promoted cooking policy."""

from __future__ import annotations

import math

from skeleton.frontier.bait import CatchBonuses
from skeleton.frontier.cooking import ActiveCookingBuff
from skeleton.frontier.energy import EnergyBoosterSpec


def _positive_multiplier(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")
    if numeric <= 0:
        raise ValueError(f"{field_name} must be positive")
    return numeric


def energy_booster_from_cooking_buff(buff: ActiveCookingBuff) -> EnergyBoosterSpec | None:
    """Project a cooking buff's immediate energy restoration into energy policy.

    Other timed cooking effects remain represented by ``ActiveCookingBuff`` and
    are intentionally not overloaded into the energy primitive.
    """

    if not isinstance(buff, ActiveCookingBuff):
        raise TypeError("buff must be an ActiveCookingBuff")
    raw_restore = buff.effects.get("energy_restore", 0)
    if isinstance(raw_restore, bool) or not isinstance(raw_restore, int):
        raise TypeError("cooking energy_restore must be an integer")
    if raw_restore < 0:
        raise ValueError("cooking energy_restore must not be negative")
    if raw_restore == 0:
        return None
    return EnergyBoosterSpec(
        id=f"cooking:{buff.recipe_id}:energy",
        name=f"{buff.name} energy restore",
        energy_restore=raw_restore,
    )


def catch_bonuses_from_cooking_buff(buff: ActiveCookingBuff) -> CatchBonuses:
    """Project only semantically compatible cooking modifiers into catch policy."""

    if not isinstance(buff, ActiveCookingBuff):
        raise TypeError("buff must be an ActiveCookingBuff")
    catch_rate = 1.0
    for key in ("catch_bonus", "all_catch_bonus"):
        if key in buff.effects:
            catch_rate *= _positive_multiplier(buff.effects[key], f"cooking {key}")
    rare = (
        _positive_multiplier(buff.effects["rare_fish_bonus"], "cooking rare_fish_bonus")
        if "rare_fish_bonus" in buff.effects
        else 1.0
    )
    legendary = (
        _positive_multiplier(buff.effects["legendary_bonus"], "cooking legendary_bonus")
        if "legendary_bonus" in buff.effects
        else 1.0
    )
    xp = (
        _positive_multiplier(buff.effects["xp_bonus"], "cooking xp_bonus")
        if "xp_bonus" in buff.effects
        else 1.0
    )
    coins = (
        _positive_multiplier(buff.effects["coin_bonus"], "cooking coin_bonus")
        if "coin_bonus" in buff.effects
        else 1.0
    )
    return CatchBonuses(
        catch_rate=catch_rate,
        rare_chance=rare,
        legendary_chance=legendary,
        xp_multiplier=xp,
        coin_multiplier=coins,
    )

"""Narrow adapters from biotope mastery into existing gameplay primitives."""

from __future__ import annotations

from skeleton.frontier.bait import CatchBonuses, combine_external_bonuses
from skeleton.frontier.biotope import (
    BiotopeMastery,
    BiotopeSpec,
    mastery_bonuses,
    weather_multiplier,
)


def compose_biotope_catch_bonuses(
    fishing: CatchBonuses,
    mastery: BiotopeMastery,
    *,
    biotope: BiotopeSpec | None = None,
    weather: str | None = None,
) -> CatchBonuses:
    """Compose mastery and optional weather into canonical catch bonuses.

    Mastery multipliers use the exact source formulas. Weather is deliberately
    applied only to catch rate because the source represents each weather value
    as one scalar environmental effect and does not define rarity/XP/coin
    semantics for it.
    """

    if not isinstance(fishing, CatchBonuses):
        raise TypeError("fishing must be CatchBonuses")
    if not isinstance(mastery, BiotopeMastery):
        raise TypeError("mastery must be BiotopeMastery")
    if (biotope is None) != (weather is None):
        raise ValueError("biotope and weather must be supplied together")

    bonuses = mastery_bonuses(mastery.level)
    external = dict(bonuses.as_external_bonuses())
    if biotope is not None and weather is not None:
        if not isinstance(biotope, BiotopeSpec):
            raise TypeError("biotope must be BiotopeSpec")
        external["catch_rate"] *= weather_multiplier(biotope, weather)
    return combine_external_bonuses(fishing, external)

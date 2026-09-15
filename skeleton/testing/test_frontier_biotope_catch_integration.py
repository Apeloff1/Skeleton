import pytest

from skeleton.frontier.bait import CatchBonuses
from skeleton.frontier.biotope import BiotopeMastery, BiotopeSpec
from skeleton.frontier.biotope_adapters import compose_biotope_catch_bonuses


def _saltwater() -> BiotopeSpec:
    return BiotopeSpec(
        "saltwater",
        "Salt Sea",
        "high",
        ("open_ocean",),
        ("dawn",),
        {"storm": 1.5, "clear": 1.0},
        15,
        True,
    )


def test_biotope_mastery_composes_multiplicatively_with_existing_catch_primitive():
    base = CatchBonuses(
        catch_rate=2.0,
        rare_chance=1.1,
        legendary_chance=1.2,
        xp_multiplier=1.5,
        coin_multiplier=2.0,
    )
    combined = compose_biotope_catch_bonuses(
        base,
        BiotopeMastery(level=10),
    )

    assert combined.catch_rate == pytest.approx(2.0 * 1.2)
    assert combined.rare_chance == pytest.approx(1.1 * 1.3)
    assert combined.legendary_chance == pytest.approx(1.2)
    assert combined.xp_multiplier == pytest.approx(1.5 * 1.1)
    assert combined.coin_multiplier == pytest.approx(2.0 * 1.15)


def test_weather_scalar_is_applied_only_to_catch_rate():
    base = CatchBonuses()
    combined = compose_biotope_catch_bonuses(
        base,
        BiotopeMastery(level=10),
        biotope=_saltwater(),
        weather="storm",
    )
    assert combined.catch_rate == pytest.approx(1.2 * 1.5)
    assert combined.rare_chance == pytest.approx(1.3)
    assert combined.xp_multiplier == pytest.approx(1.1)
    assert combined.coin_multiplier == pytest.approx(1.15)


def test_weather_context_must_be_complete():
    with pytest.raises(ValueError, match="must be supplied together"):
        compose_biotope_catch_bonuses(
            CatchBonuses(),
            BiotopeMastery(),
            biotope=_saltwater(),
        )

"""B030: genre economy presets, lint, and composition."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.genres import MMO, PRESETS, RPG, ROGUELITE, SURVIVAL, GenreEconomy, compose, lint, preset
from skeleton.simulation.economy.sim import CurrencySpec, EconomySimError, ItemSpec


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_every_preset_lints_clean_and_builds(name):
    genre = PRESETS[name]
    assert lint(genre) == []
    econ = genre.build()
    econ.open_account("p1")
    assert econ.audit()["ok"]


def test_lint_reports_open_loops():
    leaky = GenreEconomy(
        "leaky",
        currencies=(CurrencySpec("gems"),),
        items=(ItemSpec("trophy", "gems", max_stack=1),),
    )
    assert lint(leaky) == [
        "currency gems has no faucet",
        "currency gems has no sink",
        "item trophy can never be obtained",
        "item trophy can never leave the economy",
    ]
    with pytest.raises(EconomySimError, match="failed lint"):
        leaky.build()
    leaky.build(check=False)


def test_survival_weights_are_enforced():
    econ = SURVIVAL.build()
    econ.open_account("p1")
    econ.grant_items("chop", "p1", "wood", 50)
    assert econ.weight("p1") == 100
    econ.grant_items("chop", "p1", "wood", 50)
    with pytest.raises(EconomySimError):
        econ.grant_items("chop", "p1", "wood", 1)


def test_compose_dedupes_identical_specs_and_requires_tax_choice():
    with pytest.raises(EconomySimError, match="market tax"):
        compose("rpg_mmo", RPG, MMO)
    merged = compose("rpg_mmo", RPG, MMO, market_tax_bps=300)
    assert {c.currency_id for c in merged.currencies} == {"gold", "honor"}
    assert [i.item_id for i in merged.items].count("potion") == 1
    assert {"composed:rpg", "composed:mmo", "market"} <= merged.tags
    assert lint(merged) == []
    assert merged.build().market_tax_bps == 300
    survival_rogue = compose("sr", SURVIVAL, ROGUELITE)
    assert survival_rogue.default_max_weight == 200
    assert survival_rogue.default_slots == 24


def test_compose_refuses_conflicts():
    cheap_sword = GenreEconomy(
        "cheap",
        currencies=(CurrencySpec("gold"),),
        items=(ItemSpec("sword", "gold", max_stack=1, vendor_buy_price=10, vendor_sell_price=1),),
    )
    with pytest.raises(EconomySimError, match="conflicting item 'sword'"):
        compose("bad", RPG, cheap_sword)
    heavy = preset("survival", name="heavy", item_weights=(("wood", 9),))
    with pytest.raises(EconomySimError, match="conflicting weight"):
        compose("bad", SURVIVAL, heavy)
    with pytest.raises(EconomySimError, match="ceiling"):
        compose("bad", RPG, market_tax_bps=9_999)
    with pytest.raises(EconomySimError, match="unknown genre"):
        preset("mmorpg")
    with pytest.raises(EconomySimError, match="at least one"):
        compose("empty")

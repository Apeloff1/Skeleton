"""B027: ability costs as sinks, deterministic loot faucets with diminishing returns."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.combat import AbilityBook, AbilitySpec, LootEntry, LootTable
from skeleton.economy.gameplay.tests.conftest import build_econ
from skeleton.simulation.economy.sim import EconomySimError


def _book(econ):
    return AbilityBook(
        econ,
        [
            AbilitySpec("fireball", sink_id="cast"),
            AbilitySpec("heal", reagent="herb", reagent_qty=2),
            AbilitySpec("smite", sink_id="repair", base=100, reagent="herb", reagent_qty=1),
        ],
    )


def test_ability_pays_money_and_reagents_atomically():
    econ = build_econ()
    book = _book(econ)
    econ.grant("bounty", "ana", tick=0)  # 100 gold
    econ.grant_items("gather", "ana", "herb", 3)
    assert book.use("ana", "fireball")["money"] == 20
    assert book.cost("smite")["money"] == 15  # flat 5 + 10% of 100
    book.use("ana", "smite")
    assert econ.balance("ana", "gold") == 65
    assert econ.inventory("ana").count("herb") == 2
    book.use("ana", "heal")
    with pytest.raises(EconomySimError, match="missing reagents"):
        book.use("ana", "heal")
    with pytest.raises(EconomySimError, match="missing reagents"):
        book.use("ana", "smite")
    assert econ.balance("ana", "gold") == 65  # failed smite charged nothing
    assert econ.item_report("herb")["by_sink"] == {"ability:heal": 2, "ability:smite": 1}


def test_ability_without_funds_consumes_no_reagents():
    econ = build_econ()
    book = _book(econ)
    econ.grant_items("gather", "bo", "herb", 1)
    with pytest.raises(EconomySimError, match="insufficient"):
        book.use("bo", "smite")
    assert econ.inventory("bo").count("herb") == 1


def test_ability_specs_validated():
    econ = build_econ()
    with pytest.raises(EconomySimError, match="cost something"):
        AbilitySpec("free")
    with pytest.raises(EconomySimError, match="go together"):
        AbilitySpec("x", reagent="herb")
    with pytest.raises(EconomySimError, match="unknown sink"):
        AbilityBook(econ, [AbilitySpec("x", sink_id="nope")])
    with pytest.raises(EconomySimError, match="no such ability"):
        _book(econ).use("ana", "nope")


def _table(**kw):
    return LootTable(
        "goblin",
        (LootEntry("ore", weight=3, min_qty=1, max_qty=4), LootEntry("herb", weight=1)),
        rolls=kw.pop("rolls", 4),
        bounty_faucet="bounty",
        full_kills=kw.pop("full_kills", 2),
        window_ticks=100,
    )


def test_loot_is_deterministic_per_kill_and_pays_once():
    table = _table()
    assert table.roll("seed", "k1", 4) == _table().roll("seed", "k1", 4)
    econ = build_econ(slots=10)
    out = table.award(econ, "ana", "k1", tick=0, seed="seed")
    assert out["rolls"] == 4 and out["bounty"] == 100
    assert sum(out["drops"].values()) >= 4
    for item_id, qty in out["drops"].items():
        assert econ.item_report(item_id)["by_source"] == {"loot:goblin": qty}
    with pytest.raises(EconomySimError, match="already looted"):
        table.award(econ, "ana", "k1", tick=1, seed="seed")


def test_farming_hits_diminishing_returns_then_recovers():
    table = _table()
    econ = build_econ(slots=40, max_weight=10_000)
    rolls = [table.award(econ, "ana", f"k{i}", tick=i, seed="s")["rolls"] for i in range(6)]
    assert rolls == [4, 4, 2, 1, 0, 0]
    assert table.award(econ, "ana", "late", tick=200, seed="s")["rolls"] == 4
    assert table.effective_rolls("bo", 5) == 4  # per owner
    assert econ.item_audit()["ok"] and econ.audit()["ok"]


def test_full_inventory_refuses_whole_award():
    table = _table()
    econ = build_econ(slots=1)
    econ.grant_items("x", "ana", "sword", 1)
    with pytest.raises(EconomySimError, match="inventory full"):
        table.award(econ, "ana", "k1", tick=0, seed="seed")
    assert econ.balance("ana", "gold") == 0  # bounty not paid either
    econ.resize("ana", 10)
    assert table.award(econ, "ana", "k1", tick=0, seed="seed")["rolls"] == 4  # kill id still unlooted

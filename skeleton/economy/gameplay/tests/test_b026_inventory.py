"""B026: item faucets/sinks, weight limits, binding and item audit."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.core import ITEM_VENDOR_SOURCE
from skeleton.economy.gameplay.tests.conftest import build_econ
from skeleton.simulation.economy.sim import EconomySimError


def test_item_faucet_and_sink_keep_item_books(econ):
    econ.grant_items("loot", "ana", "ore", 30)
    econ.consume_items("craft", "ana", "ore", 12)
    report = econ.item_report("ore")
    assert report == {
        "item": "ore",
        "held": 18,
        "minted": 30,
        "burned": 12,
        "by_source": {"loot": 30},
        "by_sink": {"craft": 12},
    }
    assert econ.item_audit()["ok"]
    with pytest.raises(EconomySimError, match="not enough"):
        econ.consume_items("craft", "ana", "ore", 19)
    with pytest.raises(EconomySimError, match="reserved"):
        econ.grant_items(ITEM_VENDOR_SOURCE, "ana", "ore", 1)


def test_weight_limit_applies_to_every_inbound_path():
    econ = build_econ(slots=10, max_weight=30)
    econ.grant("daily", "bo", tick=0)
    econ.grant_items("loot", "ana", "sword", 2)  # 20 weight
    econ.grant_items("loot", "bo", "sword", 1)
    with pytest.raises(EconomySimError, match="inventory full"):
        econ.grant_items("loot", "ana", "ore", 11)  # 31 > 30
    econ.grant_items("loot", "ana", "ore", 10)  # exactly 30
    assert econ.weight("ana") == 30
    before = econ.snapshot()
    with pytest.raises(EconomySimError, match="destination inventory full"):
        econ.move_items("bo", "ana", "sword", 1)
    with pytest.raises(EconomySimError, match="buyer inventory full"):
        econ.trade("bo", "ana", "sword", 1, 1)
    with pytest.raises(EconomySimError, match="inventory full"):
        econ.vendor_buy("ana", "ore", 1)
    assert econ.snapshot() == before
    assert econ.max_weight("ana") == 30


def test_weight_refusal_on_vendor_buy_leaves_money(econ):
    econ.grant("daily", "ana", tick=0)
    econ.grant_items("loot", "ana", "ore", 50)
    econ.grant_items("loot", "ana", "sword", 1)
    econ.grant_items("loot", "ana", "sword", 1)
    # 50 ore + 2 swords = 70 weight in 3 slots; a third sword takes slot 4 at 80 weight
    econ.vendor_buy("ana", "sword", 1)
    assert econ.weight("ana") == 80
    econ.resize("ana", 10)
    econ.grant_items("loot", "ana", "sword", 2)  # 100 weight exactly
    before = econ.balance("ana", "gold")
    with pytest.raises(EconomySimError, match="inventory full"):
        econ.vendor_buy("ana", "ore", 1)
    assert econ.balance("ana", "gold") == before
    assert econ.item_report("sword")["by_source"] == {"loot": 4, "vendor": 1}


def test_binding_blocks_moves_and_trades_but_not_use_or_vendor(econ):
    econ.grant("daily", "bo", tick=0)
    econ.grant_items("loot", "ana", "ore", 10)
    assert econ.bind("ana", "ore", 6) == 6
    assert econ.free_count("ana", "ore") == 4
    with pytest.raises(EconomySimError, match="unbound"):
        econ.move_items("ana", "bo", "ore", 5)
    with pytest.raises(EconomySimError, match="unbound"):
        econ.trade("ana", "bo", "ore", 5, 50)
    econ.move_items("ana", "bo", "ore", 4)
    assert econ.free_count("ana", "ore") == 0
    econ.consume_items("craft", "ana", "ore", 2)
    assert econ.bound_count("ana", "ore") == 4
    econ.vendor_sell("ana", "ore", 4)
    assert econ.bound_count("ana", "ore") == 0
    with pytest.raises(EconomySimError, match="more than held"):
        econ.bind("ana", "ore", 1)
    assert econ.item_audit()["ok"] and econ.audit()["ok"]


def test_untradeable_items_and_self_moves_refused(econ):
    econ.grant_items("pvp", "ana", "badge", 1)
    with pytest.raises(EconomySimError, match="not tradeable"):
        econ.move_items("ana", "bo", "badge", 1)
    with pytest.raises(EconomySimError, match="self"):
        econ.move_items("ana", "ana", "ore", 1)


def test_move_respects_destination_capacity():
    econ = build_econ(slots=1)
    econ.grant_items("loot", "ana", "sword", 1)
    econ.grant_items("loot", "bo", "sword", 1)
    with pytest.raises(EconomySimError, match="destination inventory full"):
        econ.move_items("ana", "bo", "sword", 1)
    assert econ.inventory("ana").count("sword") == 1


def test_resize_refuses_shrink_below_use(econ):
    econ.grant_items("loot", "ana", "sword", 1)
    econ.grant_items("loot", "ana", "ore", 1)
    with pytest.raises(EconomySimError, match="shrink"):
        econ.resize("ana", 1)
    econ.resize("ana", 2)
    assert econ.inventory("ana").slots == 2


def test_charge_amount_burns_exactly_under_declared_sink(econ):
    econ.grant("daily", "ana", tick=0)
    assert econ.charge_amount("stabilizer", "ana", 37) == 37
    assert econ.flow_report("gold")["by_sink"]["stabilizer"] == 37
    with pytest.raises(EconomySimError, match="no such sink"):
        econ.charge_amount("nope", "ana", 1)
    with pytest.raises(EconomySimError, match="insufficient"):
        econ.charge_amount("stabilizer", "ana", 10_000)


def test_unknown_weight_item_rejected():
    with pytest.raises(EconomySimError, match="unknown item"):
        build_econ(weights={"ghost": 1})

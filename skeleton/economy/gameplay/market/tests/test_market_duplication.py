"""Duplicated items: serial (item-ID) conservation."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.market.errors import (
    IntegrityViolation,
    MarketError,
    OrderRejected,
)
from skeleton.economy.gameplay.market.exchange import ESCROW_OWNER
from skeleton.economy.gameplay.market.integrity import SerialRegistry
from skeleton.economy.gameplay.market.tests.conftest import funded


@pytest.fixture
def market():
    m = funded()
    m.mint_serialized("forge", "ana", "sword", ["sw-1", "sw-2"])
    m.mint_serialized("forge", "bo", "sword", ["sw-9"])
    return m


def test_serials_follow_escrow_and_settlement(market):
    market.place("ana", "sell", "sword", 1, 500, tick=1, serials=["sw-2"])
    assert market.serials.holder("sw-2") == ("sword", ESCROW_OWNER)
    b = market.place("cy", "buy", "sword", 1, 500, tick=2)
    assert b["fills"][0]["serials"] == ["sw-2"]
    assert market.serials.holder("sw-2") == ("sword", "cy")
    assert market.serials.serials_of("ana", "sword") == ["sw-1"]
    assert market.audit()["ok"]


def test_cancel_returns_serials(market):
    s = market.place("ana", "sell", "sword", 2, 500, tick=1, serials=["sw-1", "sw-2"])
    market.cancel("ana", s["order_id"], tick=50)
    assert market.serials.serials_of("ana", "sword") == ["sw-1", "sw-2"]
    assert market.audit()["ok"]


@pytest.mark.parametrize(
    "serials, why",
    [
        (["sw-9"], "held by someone else"),
        (["sw-404"], "unknown serial"),
        (["sw-1", "sw-1"], "repeated"),
        ([], "count does not match"),
    ],
)
def test_bad_serials_are_refused_and_logged(market, serials, why):
    qty = max(1, len(serials))
    with pytest.raises(OrderRejected, match=why):
        market.place("ana", "sell", "sword", qty, 500, tick=1, serials=serials)
    (inc,) = market.incidents.of("duplicate")
    assert why in inc["reason"]
    assert market.econ.inventory("ana").count("sword") == 2
    assert market.audit()["ok"]


def test_same_serial_cannot_be_listed_twice(market):
    market.place("ana", "sell", "sword", 1, 500, tick=1, serials=["sw-1"])
    with pytest.raises(OrderRejected, match="held by someone else"):
        market.place("ana", "sell", "sword", 1, 500, tick=2, serials=["sw-1"])


def test_duplicate_mint_refused(market):
    with pytest.raises(MarketError):
        market.mint_serialized("forge", "cy", "sword", ["sw-1"])
    assert market.incidents.of("duplicate")
    assert market.econ.inventory("cy").count("sword") == 0


def test_unregistered_copy_breaks_audit(market):
    market.econ.grant_items("exploit", "cy", "sword", 1)
    report = market.audit()
    assert not report["ok"] and not report["checks"]["serials"]
    assert report["serial_problems"] == [
        {"holder": "cy", "item": "sword", "serials": 0, "held": 1}
    ]


def test_registry_unit_rules():
    reg = SerialRegistry(["sword"])
    reg.register("sword", "a", "s1")
    with pytest.raises(IntegrityViolation):
        reg.register("sword", "b", "s1")
    with pytest.raises(MarketError):
        reg.register("ore", "a", "o1")
    assert reg.problem("ore", "a", ["x"], 1) == "serials given for non-serialized item"
    assert reg.problem("ore", "a", [], 3) is None
    reg.retire("s1")
    assert reg.holder("s1") is None
    clone = SerialRegistry.from_state(reg.to_state())
    assert clone.to_state() == reg.to_state()

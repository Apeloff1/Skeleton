"""Price manipulation: out-of-band prints and spoofing."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.market.errors import OrderRejected
from skeleton.economy.gameplay.market.integrity import ManipulationMonitor
from skeleton.economy.gameplay.market.tests.conftest import funded


def _with_swords():
    market = funded()
    market.mint_serialized("forge", "ana", "sword", ["sw-1", "sw-2"])
    return market


def test_out_of_band_resting_order_is_cancelled_not_printed():
    market = _with_swords()
    econ = market.econ
    s = market.place("ana", "sell", "sword", 1, 900, tick=1, serials=["sw-1"])
    b = market.place("bo", "buy", "sword", 1, 900, tick=2)
    assert b["fills"] == [] and b["status"] == "open"
    (inc,) = market.incidents.of("out_of_band")
    assert inc["order_id"] == s["order_id"] and inc["reference"] == 500
    assert econ.inventory("ana").count("sword") == 2
    assert market.serials.holder("sw-1") == ("sword", "ana")
    assert market.audit()["ok"]


def test_in_band_print_moves_reference_by_ema():
    market = funded()
    market.place("ana", "sell", "herb", 1, 25, tick=1)
    market.place("bo", "buy", "herb", 1, 25, tick=1)
    assert market.monitor.reference("herb") == 20 + (25 - 20) * 2_000 // 10_000


def test_band_walks_only_slowly():
    market = funded()
    for t in range(1, 30):
        ref = market.monitor.reference("herb")
        lo, hi = market.monitor.band("herb")
        market.place("ana", "sell", "herb", 1, hi, tick=t)
        market.place("bo", "buy", "herb", 1, hi, tick=t)
        assert market.monitor.reference("herb") > ref
    assert market.monitor.reference("herb") < 20 * 10
    assert not market.incidents.of("out_of_band")


def test_low_ball_print_refused(market):
    market.place("ana", "sell", "ore", 5, 1, tick=1)
    b = market.place("bo", "buy", "ore", 5, 10, tick=2)
    assert b["fills"] == [] and market.incidents.of("out_of_band")
    assert market.econ.inventory("ana").count("ore") == 50
    assert market.audit()["ok"]


def test_spoofer_is_restricted_after_fast_cancels():
    market = funded(spoof_min_orders=3, spoof_ticks=5, penalty_ticks=100)
    ids = [
        market.place("ana", "buy", "ore", 50, 9, tick=10)["order_id"] for _ in range(3)
    ]
    flagged = [market.cancel("ana", oid, tick=12)["spoof_flagged"] for oid in ids]
    assert flagged == [False, False, True]
    (inc,) = market.incidents.of("spoof")
    assert inc["owner"] == "ana" and inc["until"] == 112
    with pytest.raises(OrderRejected):
        market.place("ana", "buy", "ore", 1, 9, tick=50)
    market.place("ana", "buy", "ore", 1, 9, tick=112)
    assert market.audit()["ok"]


def test_slow_or_filled_cancels_are_not_spoofing():
    market = funded(spoof_min_orders=2, spoof_ticks=5)
    a = market.place("ana", "buy", "ore", 10, 9, tick=1)
    b = market.place("ana", "buy", "ore", 10, 9, tick=1)
    assert not market.cancel("ana", a["order_id"], tick=20)["spoof_flagged"]
    market.place("bo", "sell", "ore", 9, 9, tick=21)
    assert not market.cancel("ana", b["order_id"], tick=22)["spoof_flagged"]
    assert not market.incidents.of("spoof")


def test_monitor_state_round_trip():
    mon = ManipulationMonitor()
    mon.seed("ore", 10)
    mon.on_place("a", 1, 100)
    mon.on_cancel("a", 2, 1, 5, 5, 100)
    clone = ManipulationMonitor.from_state(mon.to_state())
    assert clone.to_state() == mon.to_state()
    assert clone.band("ore") == (7, 13)

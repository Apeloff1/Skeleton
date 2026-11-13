"""Wash trading: same owner or linked circle on both sides."""

from __future__ import annotations

from skeleton.economy.gameplay.market.exchange import ESCROW_OWNER
from skeleton.economy.gameplay.market.integrity import AccountLinks, WashTradeDetector
from skeleton.economy.gameplay.market.tests.conftest import funded


def test_self_trade_cancels_incoming_and_refunds(market):
    econ = market.econ
    s = market.place("ana", "sell", "ore", 5, 10, tick=1)
    before = econ.balance("ana", "gold")
    b = market.place("ana", "buy", "ore", 5, 10, tick=2)
    assert b["status"] == "wash_cancelled" and b["fills"] == []
    assert econ.balance("ana", "gold") == before - b["fee"]
    assert market.book.get(s["order_id"]).remaining == 5
    (inc,) = market.incidents.of("wash")
    assert inc["incoming"] == "ana" and inc["resting"] == "ana"
    assert econ.balance(ESCROW_OWNER, "gold") == 0
    assert market.audit()["ok"]


def test_declared_link_blocks_alt_account_fill(market):
    market.wash.links.link("ana", "bo", "alt")
    market.place("ana", "sell", "ore", 5, 10, tick=1)
    b = market.place("bo", "buy", "ore", 5, 10, tick=2)
    assert b["status"] == "wash_cancelled"
    c = market.place("cy", "buy", "ore", 5, 10, tick=3)
    assert c["status"] == "filled"
    assert market.audit()["ok"]


def test_wash_stops_matching_but_keeps_earlier_fills(market):
    market.place("cy", "sell", "ore", 2, 10, tick=1)
    market.place("ana", "sell", "ore", 2, 11, tick=1)
    b = market.place("ana", "buy", "ore", 4, 11, tick=2)
    assert [f["seller"] for f in b["fills"]] == ["cy"]
    assert b["status"] == "wash_cancelled"
    assert market.audit()["ok"]


def test_circular_trading_links_the_circle():
    market = funded()
    for t, (seller, buyer) in enumerate(
        [("ana", "bo"), ("bo", "cy"), ("cy", "ana")], start=1
    ):
        market.place(seller, "sell", "herb", 1, 20, tick=t)
        market.place(buyer, "buy", "herb", 1, 20, tick=t)
    (inc,) = market.incidents.of("circular")
    assert inc["owners"] == ["ana", "bo", "cy"]
    assert market.wash.links.linked("ana", "cy") and market.wash.links.linked(
        "bo", "cy"
    )
    market.place("ana", "sell", "herb", 1, 20, tick=10)
    assert (
        market.place("cy", "buy", "herb", 1, 20, tick=11)["status"] == "wash_cancelled"
    )
    assert market.place("dee", "buy", "herb", 1, 20, tick=12)["status"] == "filled"


def test_cycle_window_expires():
    det = WashTradeDetector(cycle_ticks=10)
    assert det.observe(0, "ore", "a", "b") is None
    assert det.observe(100, "ore", "b", "a") is None
    assert det.observe(105, "ore", "a", "b") == ["a", "b"]


def test_cycle_length_limit():
    det = WashTradeDetector(max_cycle=3)
    for s, b in [("a", "b"), ("b", "c"), ("c", "d")]:
        assert det.observe(1, "ore", s, b) is None
    assert det.observe(2, "ore", "d", "a") is None  # 4-cycle exceeds limit
    assert det.observe(3, "ore", "c", "a") == ["a", "b", "c"]


def test_links_are_transitive_and_round_trip():
    links = AccountLinks()
    links.link("b", "c")
    links.link("a", "b", "device")
    assert links.linked("a", "c")
    assert links.circle("c") == ["a", "b", "c"]
    clone = AccountLinks.from_state(links.to_state())
    assert clone.linked("a", "c") and not clone.linked("a", "d")

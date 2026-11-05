"""Escrow and settlement: nothing is created or destroyed outside declared sinks."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.market.errors import MarketError, OrderRejected
from skeleton.economy.gameplay.market.exchange import (
    ESCROW_OWNER,
    MarketConfig,
    PlayerMarket,
)
from skeleton.economy.gameplay.market.tests.conftest import (
    OWNERS,
    build_econ,
    config,
    funded,
)


def _totals(market):
    econ = market.econ
    owners = [*OWNERS, ESCROW_OWNER]
    money = sum(econ.balance(o, "gold") for o in owners)
    ore = sum(econ.inventory(o).count("ore") for o in owners)
    return money, ore


def test_sell_offer_escrows_items_and_burns_fee(market):
    econ = market.econ
    before = econ.balance("ana", "gold")
    res = market.place("ana", "sell", "ore", 10, 11, tick=1)
    assert res["status"] == "open" and res["resting"] == 10
    assert res["fee"] == market.listing_fee(110)
    assert econ.balance("ana", "gold") == before - res["fee"]
    assert econ.inventory("ana").count("ore") == 40
    assert econ.inventory(ESCROW_OWNER).count("ore") == 10
    assert market.audit()["ok"]


def test_buy_request_escrows_money(market):
    econ = market.econ
    res = market.place("bo", "buy", "ore", 5, 10, tick=1)
    assert econ.balance(ESCROW_OWNER, "gold") == 50
    assert econ.balance("bo", "gold") == 10_000 - 50 - res["fee"]
    assert market.audit()["ok"]


def test_fill_moves_goods_money_and_burns_only_declared_sinks(market):
    econ = market.econ
    money0, ore0 = _totals(market)
    burned0 = econ.flow_report("gold")["burned"]
    s = market.place("ana", "sell", "ore", 10, 11, tick=1)
    b = market.place("bo", "buy", "ore", 10, 11, tick=2)
    assert b["status"] == "filled" and len(b["fills"]) == 1
    fill = b["fills"][0]
    assert (
        fill["price"] == 11
        and fill["qty"] == 10
        and fill["tax"] == market.sales_tax(110)
    )
    assert econ.inventory("bo").count("ore") == 60
    sinks = s["fee"] + b["fee"] + fill["tax"]
    money1, ore1 = _totals(market)
    assert ore1 == ore0
    assert money0 - money1 == sinks
    assert econ.flow_report("gold")["burned"] - burned0 == sinks
    assert market.sink_report() == {
        "listing_fees": s["fee"] + b["fee"],
        "sales_tax": fill["tax"],
    }
    assert market.audit()["ok"]


def test_maker_price_and_buyer_price_improvement(market):
    econ = market.econ
    market.place("ana", "sell", "ore", 4, 10, tick=1)
    before = econ.balance("bo", "gold")
    b = market.place("bo", "buy", "ore", 4, 13, tick=2)
    assert b["fills"][0]["price"] == 10
    assert econ.balance("bo", "gold") == before - b["fee"] - 40
    assert econ.balance(ESCROW_OWNER, "gold") == 0
    assert market.audit()["ok"]


def test_partial_fills_walk_the_book_in_priority_order(market):
    market.place("ana", "sell", "ore", 3, 11, tick=1)
    market.place("cy", "sell", "ore", 3, 10, tick=2)
    market.place("dee", "sell", "ore", 3, 10, tick=3)
    b = market.place("bo", "buy", "ore", 8, 11, tick=4)
    assert [(f["seller"], f["qty"], f["price"]) for f in b["fills"]] == [
        ("cy", 3, 10),
        ("dee", 3, 10),
        ("ana", 2, 11),
    ]
    assert b["status"] == "filled"
    assert market.book.best("ore", "sell").remaining == 1
    assert market.audit()["ok"]


def test_resting_remainder_after_partial_fill(market):
    market.place("ana", "sell", "ore", 2, 10, tick=1)
    b = market.place("bo", "buy", "ore", 5, 10, tick=2)
    assert b["resting"] == 3 and b["status"] == "open"
    assert market.econ.balance(ESCROW_OWNER, "gold") == 30
    assert market.audit()["ok"]


def test_ioc_remainder_is_refunded(market):
    econ = market.econ
    market.place("ana", "sell", "ore", 2, 10, tick=1)
    before = econ.balance("bo", "gold")
    b = market.place("bo", "buy", "ore", 5, 10, tick=2, tif="ioc")
    assert b["status"] == "ioc_cancelled" and b["resting"] == 0
    assert econ.balance("bo", "gold") == before - b["fee"] - 20
    assert econ.balance(ESCROW_OWNER, "gold") == 0
    assert market.audit()["ok"]


def test_cancel_returns_escrow_but_not_fee(market):
    econ = market.econ
    s = market.place("ana", "sell", "ore", 10, 11, tick=1)
    b = market.place("bo", "buy", "herb", 2, 20, tick=1)
    market.cancel("ana", s["order_id"], tick=50)
    market.cancel("bo", b["order_id"], tick=50)
    assert econ.inventory("ana").count("ore") == 50
    assert econ.balance("ana", "gold") == 10_000 - s["fee"]
    assert econ.balance("bo", "gold") == 10_000 - b["fee"]
    with pytest.raises(OrderRejected):
        market.cancel("ana", s["order_id"], tick=51)
    assert market.audit()["ok"]


def test_cancel_someone_elses_order_refused(market):
    s = market.place("ana", "sell", "ore", 1, 11, tick=1)
    with pytest.raises(OrderRejected):
        market.cancel("bo", s["order_id"], tick=2)


def test_orders_expire_and_refund():
    market = funded(default_ttl=10)
    market.place("ana", "sell", "ore", 5, 11, tick=0)
    market.place("bo", "buy", "ore", 5, 9, tick=0)
    market.advance(10)
    assert len(market.book) == 0
    assert market.econ.inventory("ana").count("ore") == 50
    assert market.econ.balance(ESCROW_OWNER, "gold") == 0
    assert market.audit()["ok"]


def test_full_bags_become_claims_held_in_escrow():
    market = funded(econ_kw={"slots": 2})
    econ = market.econ
    market.place("ana", "sell", "ore", 5, 10, tick=1)
    # a one-slot buyer whose only slot is taken by herbs
    econ.open_account("eve", slots=1)
    econ.grant("daily", "eve", tick=0)
    econ.grant_items("garden", "eve", "herb", 1)
    b = market.place("eve", "buy", "ore", 5, 10, tick=2)
    assert b["fills"][0]["claimed"] == 5
    assert market.claims == {"eve": {"ore": 5}}
    assert econ.inventory(ESCROW_OWNER).count("ore") == 5
    assert market.audit()["ok"]
    with pytest.raises(OrderRejected):
        market.claim("eve", "ore", tick=3)
    econ.consume_items("eat", "eve", "herb", 1)
    assert market.claim("eve", "ore", tick=4) == 5
    assert market.claims == {}
    assert econ.inventory("eve").count("ore") == 5
    assert market.audit()["ok"]


def test_refusals_change_nothing(market):
    econ = market.econ
    econ_digest = econ.digest()
    with pytest.raises(OrderRejected):
        market.place("ana", "sell", "ore", 51, 10, tick=1)
    with pytest.raises(OrderRejected):
        market.place("ana", "buy", "ore", 1_000, 10, tick=1)
    with pytest.raises(OrderRejected):
        market.place("ana", "sell", "badge", 1, 10, tick=1)
    with pytest.raises(OrderRejected):
        market.place(ESCROW_OWNER, "sell", "ore", 1, 10, tick=1)
    with pytest.raises(OrderRejected):
        market.place("zed", "sell", "ore", 1, 10, tick=1)
    with pytest.raises(OrderRejected):
        market.place("ana", "lend", "ore", 1, 10, tick=1)
    assert econ.balance("ana", "gold") == 10_000
    # refusals may only advance the clock; books are untouched
    assert market.audit()["ok"] and len(market.book) == 0
    assert market.econ.digest() == econ_digest


def test_bound_items_cannot_be_listed(market):
    econ = market.econ
    econ.bind("ana", "ore", 50)
    with pytest.raises(OrderRejected):
        market.place("ana", "sell", "ore", 1, 10, tick=1)


def test_tick_cannot_go_backwards(market):
    market.place("ana", "sell", "ore", 1, 10, tick=10)
    with pytest.raises(MarketError):
        market.place("ana", "sell", "ore", 1, 10, tick=9)


def test_open_order_cap():
    market = funded(max_open_orders=2)
    market.place("ana", "sell", "ore", 1, 11, tick=1)
    market.place("ana", "sell", "ore", 1, 11, tick=1)
    with pytest.raises(OrderRejected):
        market.place("ana", "sell", "ore", 1, 11, tick=1)


def test_config_must_name_declared_sinks():
    econ = build_econ()
    with pytest.raises(MarketError):
        PlayerMarket(econ, config(listing_sink="nope"))
    with pytest.raises(MarketError):
        PlayerMarket(econ, config(sales_tax_sink="market_listing"))
    with pytest.raises(MarketError):
        PlayerMarket(econ, MarketConfig("honor", "market_listing", "market_sales_tax"))

"""Listing fees and sales tax are economy sinks, visible in the flow report."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.market.errors import OrderRejected
from skeleton.economy.gameplay.market.tests.conftest import funded


def test_listing_fee_is_flat_plus_bps_rounded_up(market):
    assert market.listing_fee(0) == 1
    assert market.listing_fee(100) == 2
    assert market.listing_fee(101) == 3
    assert market.sales_tax(100) == 5
    assert market.sales_tax(1) == 1


def test_fees_show_up_as_named_sinks_in_flow_report(market):
    market.place("ana", "sell", "ore", 10, 10, tick=1)
    market.place("bo", "buy", "ore", 10, 10, tick=2)
    flows = market.econ.flow_report("gold")["by_sink"]
    assert flows["market_listing"] == 2 * market.listing_fee(100)
    assert flows["market_sales_tax"] == market.sales_tax(100)
    assert market.econ.audit()["ok"]


def test_tax_is_charged_per_fill_from_seller(market):
    econ = market.econ
    market.place("cy", "buy", "ore", 3, 10, tick=1)
    market.place("dee", "buy", "ore", 3, 10, tick=1)
    before = econ.balance("ana", "gold")
    s = market.place("ana", "sell", "ore", 6, 10, tick=2)
    taxes = [f["tax"] for f in s["fills"]]
    assert taxes == [market.sales_tax(30), market.sales_tax(30)]
    assert econ.balance("ana", "gold") == before - s["fee"] + 60 - sum(taxes)


def test_fee_must_be_affordable_for_sells():
    market = funded()
    econ = market.econ
    econ.open_account("poor")
    econ.grant_items("mine", "poor", "ore", 5)
    with pytest.raises(OrderRejected):
        market.place("poor", "sell", "ore", 5, 10, tick=1)
    assert econ.inventory("poor").count("ore") == 5


def test_buy_needs_escrow_plus_fee(market):
    econ = market.econ
    econ.open_account("eve")
    econ.grant("daily", "eve", tick=0)
    with pytest.raises(OrderRejected):
        market.place("eve", "buy", "ore", 1_000, 10, tick=1)
    assert econ.balance("eve", "gold") == 10_000


def test_zero_tax_sink_config_is_rejected_by_sinkspec():
    from skeleton.simulation.economy.sim import EconomySimError, SinkSpec

    with pytest.raises(EconomySimError):
        SinkSpec("market_sales_tax", "gold")


def test_sink_to_faucet_ratio_moves_with_market_activity():
    market = funded()
    econ = market.econ
    r0 = econ.flow_report("gold")["sink_to_faucet_bps"]
    for t in range(1, 6):
        market.place("ana", "sell", "ore", 5, 10, tick=t)
        market.place("bo", "buy", "ore", 5, 10, tick=t)
    assert econ.flow_report("gold")["sink_to_faucet_bps"] > r0
    assert market.audit()["ok"]

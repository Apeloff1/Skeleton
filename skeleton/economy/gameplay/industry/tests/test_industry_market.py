"""Market wiring, pricing and inflation telemetry."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.industry.engine import IndustrySystem
from skeleton.economy.gameplay.industry.errors import IndustryError
from skeleton.economy.gameplay.industry.tests.conftest import (
    BLUEPRINTS,
    NODES,
    build_system,
    config,
    stocked,
)


def test_value_uses_market_then_vendor_then_zero():
    s = build_system(market=True)
    assert s.value_of("ingot") == 50
    assert s.value_of("ore") == 10  # vendor midpoint (12 + 8) // 2
    assert build_system().value_of("hull") == 0
    assert s.install_fee("smelt_ingot", 2) == 2 + 100 * 100 // 10_000


def test_craft_then_sell_and_buy_inputs_through_market():
    s = stocked(market=True)
    s.queue_build("ana", "smelt_ingot", 4, tick=0)
    s.advance(40)
    s.list_output("ana", "ingot", 4, 55, tick=41)
    s.buy_inputs("bo", "ingot", 4, 60, tick=42)
    assert s.econ.inventory("bo").count("ingot") == 4
    s.queue_build("bo", "press_plate", 1, tick=43)
    assert s.jobs("bo")[0]["status"] == "running"
    assert s.market.history.last_price("ingot") == 55
    assert s.audit()["ok"] and s.audit()["checks"]["market"]


def test_market_needs_same_economy_and_distinct_sinks():
    other = build_system(market=True)
    with pytest.raises(IndustryError):
        IndustrySystem(
            build_system().econ, config(), BLUEPRINTS, NODES, market=other.market
        )
    with pytest.raises(Exception):
        IndustrySystem(
            other.econ,
            config(install_sink="market_listing"),
            BLUEPRINTS,
            NODES,
            market=other.market,
        )
    with pytest.raises(IndustryError):
        build_system().list_output("ana", "ingot", 1, 1, tick=0)


def test_telemetry_closes_periods_with_supply_and_price_index():
    s = stocked(market=True)
    s.queue_build("ana", "smelt_ingot", 2, tick=0)
    s.extract("bo", "vein_a", tick=5)
    s.advance(20)
    s.list_output("ana", "ingot", 1, 50, tick=21)
    s.buy_inputs("bo", "ingot", 1, 50, tick=22)
    s.advance(250)
    rows = s.telemetry.rows
    assert [r["period"] for r in rows] == [0]
    row = rows[0]
    assert row["extracted"] == 20 and row["crafted"] == 2 and row["lost"] == 2
    assert row["install_fees"] == s.sink_report()["install_fees"]
    assert row["money_supply"] == s.econ.flow_report("gold")["circulating"]
    assert (
        row["price_index_bps"] == -1
    )  # market has not closed a period yet: no base prices
    assert row["money_sink_bps"] == row["install_fees"] * 10_000 // row["money_supply"]
    s.list_output(
        "ana", "ingot", 1, 60, tick=260
    )  # market closes its periods and sets bases
    s.buy_inputs("bo", "ingot", 1, 60, tick=261)
    s.queue_build("ana", "smelt_ingot", 1, tick=262)
    s.advance(400)
    assert (
        s.telemetry.rows[-1]["price_index_bps"] == s.market.telemetry.price_index() > 0
    )


def test_telemetry_without_market_has_no_index():
    s = stocked()
    s.queue_build("ana", "smelt_ingot", 1, tick=0)
    s.advance(150)
    assert s.telemetry.rows[0]["price_index_bps"] == -1

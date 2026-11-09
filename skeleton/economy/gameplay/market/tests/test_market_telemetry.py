"""Inflation telemetry: money supply, velocity, price index."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.market.errors import MarketError
from skeleton.economy.gameplay.market.exchange import ESCROW_OWNER
from skeleton.economy.gameplay.market.telemetry import InflationTelemetry
from skeleton.economy.gameplay.market.tests.conftest import funded


def _trade(market, item, qty, price, tick):
    market.place("ana", "sell", item, qty, price, tick=tick)
    market.place("bo", "buy", item, qty, price, tick=tick)


def test_period_row_reports_supply_escrow_velocity():
    market = funded()
    _trade(market, "ore", 10, 10, 1)
    market.place("cy", "buy", "herb", 5, 18, tick=2)  # rests, 90 gold escrowed
    (row,) = market.advance(100)
    supply = market.econ.flow_report("gold")["circulating"]
    assert row["period"] == 0
    assert row["money_supply"] == supply
    assert row["escrowed"] == 90 == market.balance(ESCROW_OWNER)
    assert row["player_held"] == supply - 90
    assert row["turnover"] == 100 and row["fills"] == 1
    assert row["velocity_bps"] == 100 * 10_000 // supply
    assert row["sinks"] == row["listing_fees"] + row["sales_tax"]


def test_price_index_tracks_basket_vwaps():
    market = funded()
    _trade(market, "ore", 1, 10, 1)
    _trade(market, "herb", 1, 20, 1)
    (r0,) = market.advance(100)
    assert r0["price_index_bps"] == 10_000
    _trade(market, "ore", 1, 12, 101)
    (r1,) = market.advance(200)
    base = 10 * 10 + 5 * 20
    assert r1["price_index_bps"] == (10 * 12 + 5 * 20) * 10_000 // base
    assert market.telemetry.inflation_bps() == r1["price_index_bps"] - 10_000


def test_index_unknown_until_basket_priced():
    market = funded()
    _trade(market, "ore", 1, 10, 1)
    (row,) = market.advance(100)
    assert row["price_index_bps"] == -1
    assert market.telemetry.inflation_bps() is None


def test_skipped_periods_emit_one_row_for_the_open_period():
    market = funded()
    _trade(market, "ore", 1, 10, 1)
    rows = market.advance(550)
    assert [r["period"] for r in rows] == [0]
    assert (
        market.telemetry.pending_period() is None
        or market.telemetry.pending_period() >= 5
    )


def test_unit_rules_and_round_trip():
    t = InflationTelemetry("gold", {"ore": 1})
    t.on_fill(0, "ore", 10, 2, 1)
    t.on_fee(0, 3)
    row = t.close(0, 1_000, 0, {"ore": 10})
    assert row["velocity_bps"] == 200 and row["sinks"] == 4
    with pytest.raises(MarketError):
        t.close(0, 1_000, 0, {})
    clone = InflationTelemetry.from_state(t.to_state())
    assert clone.to_state() == t.to_state()
    assert t.close(1, 0, 0, {})["velocity_bps"] == 0

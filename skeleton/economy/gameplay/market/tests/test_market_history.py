"""Price history: OHLC, volume, VWAP per period."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.market.errors import MarketError
from skeleton.economy.gameplay.market.history import PriceHistory


def test_ohlc_within_one_period():
    h = PriceHistory(period_ticks=10)
    for tick, price, qty in [(0, 10, 2), (3, 13, 1), (5, 8, 4), (9, 11, 3)]:
        h.record("ore", tick, price, qty)
    (c,) = h.candles("ore")
    assert (c["open"], c["high"], c["low"], c["close"]) == (10, 13, 8, 11)
    assert c["volume"] == 10 and c["prints"] == 4
    assert c["notional"] == 20 + 13 + 32 + 33
    assert c["vwap"] == 98 // 10


def test_new_period_starts_new_candle_and_gaps_fill_flat():
    h = PriceHistory(period_ticks=10)
    h.record("ore", 1, 10, 1)
    h.record("ore", 35, 12, 1)
    assert [c["period"] for c in h.candles("ore")] == [0, 3]
    filled = h.candles("ore", fill_gaps=True)
    assert [c["period"] for c in filled] == [0, 1, 2, 3]
    assert filled[1]["volume"] == 0 and filled[1]["close"] == 10
    assert h.candles("ore", since_period=3)[0]["open"] == 12


def test_retention_and_vwap_over_periods():
    h = PriceHistory(period_ticks=1, retain=3)
    for t in range(5):
        h.record("ore", t, 10 + t, 1)
    assert [c["period"] for c in h.candles("ore")] == [2, 3, 4]
    assert h.vwap("ore", 2) == (13 + 14) // 2
    assert h.vwap("herb", 2) is None
    assert h.last_price("ore") == 14


def test_backwards_and_bad_input():
    h = PriceHistory(period_ticks=10)
    h.record("ore", 5, 10, 1)
    with pytest.raises(MarketError):
        h.record("ore", 4, 10, 1)
    with pytest.raises(Exception):
        h.record("ore", 6, 0, 1)


def test_state_round_trip():
    h = PriceHistory(period_ticks=10)
    h.record("ore", 1, 10, 2)
    h.record("herb", 12, 20, 1)
    clone = PriceHistory.from_state(h.to_state())
    assert clone.to_state() == h.to_state()
    assert clone.notional_in_period(1) == 20


def test_market_records_history_from_fills(market):
    market.place("ana", "sell", "ore", 5, 10, tick=1)
    market.place("bo", "buy", "ore", 2, 10, tick=2)
    market.place("cy", "buy", "ore", 3, 11, tick=150)
    candles = market.history.candles("ore")
    assert [(c["period"], c["volume"], c["close"]) for c in candles] == [
        (0, 2, 10),
        (1, 3, 10),
    ]
    assert market.quote("ore")["last"] == 10


def test_sparse_candle_gap_expansion_is_bounded_before_allocation(monkeypatch):
    from skeleton.economy.gameplay.market import history as history_module

    monkeypatch.setattr(history_module, "MAX_FILLED_CANDLES", 4)
    h = PriceHistory(period_ticks=1)
    h.record("ore", 0, 10, 1)
    h.record("ore", 1000000, 12, 1)
    assert [c["period"] for c in h.candles("ore")] == [0, 1000000]
    with pytest.raises(MarketError, match="output bound"):
        h.candles("ore", fill_gaps=True)
    assert len(h.candles("ore")) == 2

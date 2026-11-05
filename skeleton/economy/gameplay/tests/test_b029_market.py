"""B029: player-market integrity guard (price band, wash trades, velocity)."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.market import MarketGuard, MarketIntegrityError
from skeleton.economy.gameplay.tests.conftest import build_econ


def _setup(**guard_kw):
    econ = build_econ(owners=("ana", "bo", "cy"), slots=10, max_weight=1_000)
    for who in ("ana", "bo", "cy"):
        econ.grant("daily", who, tick=0)
        econ.grant_items("mine", who, "ore", 50)
    return econ, MarketGuard(econ, **guard_kw)


def test_reference_seeded_from_vendor_midpoint_and_band_enforced():
    econ, guard = _setup()
    assert guard.reference("ore") == 7
    assert guard.band("ore") == (5, 9)
    guard.fill("ana", "bo", "ore", 10, 80, tick=1)  # unit 8 in band
    with pytest.raises(MarketIntegrityError, match="outside band"):
        guard.fill("ana", "cy", "ore", 10, 500, tick=2)  # RMT-style gold transfer
    with pytest.raises(MarketIntegrityError, match="outside band"):
        guard.fill("ana", "cy", "ore", 10, 10, tick=2)
    assert econ.balance("cy", "gold") == 1_000  # refused fills move nothing
    assert [r["reason"] for r in guard.refusals()] == ["price outside band", "price outside band"]


def test_reference_follows_accepted_fills_slowly():
    _, guard = _setup()
    guard.fill("ana", "bo", "ore", 10, 90, tick=1)  # unit 9
    assert guard.reference("ore") == 7  # 7 + 2*20% floors to 7
    guard.set_reference("ore", 100)
    guard.fill("ana", "cy", "ore", 1, 130, tick=2)
    assert guard.reference("ore") == 106


def test_round_trip_wash_trade_refused_within_window():
    _, guard = _setup(round_trip_ticks=50)
    guard.fill("ana", "bo", "ore", 5, 35, tick=1)
    with pytest.raises(MarketIntegrityError, match="round-trip"):
        guard.fill("bo", "ana", "ore", 5, 35, tick=20)
    guard.fill("bo", "ana", "ore", 5, 35, tick=60)  # outside the window


def test_velocity_limit_per_participant():
    _, guard = _setup(max_fills=3, window_ticks=10, round_trip_ticks=0)
    guard.fill("ana", "bo", "ore", 1, 7, tick=1)
    guard.fill("ana", "cy", "ore", 1, 7, tick=2)
    guard.fill("ana", "bo", "ore", 1, 7, tick=3)
    with pytest.raises(MarketIntegrityError, match="velocity"):
        guard.fill("cy", "ana", "ore", 1, 7, tick=4)
    guard.fill("ana", "bo", "ore", 1, 7, tick=11)


def test_unpriced_items_need_discovery_and_ticks_are_monotonic():
    econ, guard = _setup()
    econ.grant_items("x", "ana", "herb", 2)
    with pytest.raises(MarketIntegrityError, match="no reference"):
        guard.fill("ana", "bo", "herb", 1, 10, tick=1)
    econ2, open_guard = _setup(allow_discovery=True)
    econ2.grant_items("x", "ana", "herb", 2)
    open_guard.fill("ana", "bo", "herb", 1, 10, tick=1)
    assert open_guard.reference("herb") == 10
    with pytest.raises(MarketIntegrityError, match="backwards"):
        open_guard.fill("ana", "bo", "herb", 1, 10, tick=0)
    assert econ2.audit()["ok"] and econ2.item_audit()["ok"]

"""Shared fixtures for the gameplay economy tests."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.core import GameplayEconomy
from skeleton.simulation.economy.sim import CurrencySpec, FaucetSpec, ItemSpec, SinkSpec


def build_econ(**kw) -> GameplayEconomy:
    econ = GameplayEconomy(
        currencies=[CurrencySpec("gold", supply_cap=kw.pop("cap", None)), CurrencySpec("honor", tradeable=False)],
        items=[
            ItemSpec("ore", "gold", max_stack=50, vendor_buy_price=10, vendor_sell_price=5),
            ItemSpec("sword", "gold", max_stack=1, vendor_buy_price=400, vendor_sell_price=100),
            ItemSpec("herb", "gold", max_stack=20),
            ItemSpec("badge", "honor", max_stack=1, tradeable=False),
        ],
        faucets=[
            FaucetSpec("bounty", "gold", amount=100, cooldown_ticks=kw.pop("bounty_cd", 0)),
            FaucetSpec("daily", "gold", amount=1_000, cooldown_ticks=100),
            FaucetSpec("arena", "honor", amount=10),
        ],
        sinks=[
            SinkSpec("repair", "gold", flat=5, bps=1_000),
            SinkSpec("upkeep", "gold", flat=50),
            SinkSpec("stabilizer", "gold", flat=1),
            SinkSpec("cast", "gold", flat=20),
        ],
        market_tax_bps=kw.pop("tax", 500),
        default_slots=kw.pop("slots", 4),
        item_weights=kw.pop("weights", {"ore": 1, "sword": 10, "herb": 0}),
        default_max_weight=kw.pop("max_weight", 100),
    )
    for owner in kw.pop("owners", ("ana", "bo")):
        econ.open_account(owner)
    return econ


@pytest.fixture
def econ() -> GameplayEconomy:
    return build_econ()

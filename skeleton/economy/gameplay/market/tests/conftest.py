"""Shared fixtures for the player-market tests."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.core import GameplayEconomy
from skeleton.economy.gameplay.market.exchange import MarketConfig, PlayerMarket
from skeleton.simulation.economy.sim import CurrencySpec, FaucetSpec, ItemSpec, SinkSpec

OWNERS = ("ana", "bo", "cy", "dee")


def build_econ(
    owners=OWNERS, *, slots: int = 8, listing_bps: int = 100, tax_bps: int = 500
) -> GameplayEconomy:
    econ = GameplayEconomy(
        currencies=[CurrencySpec("gold"), CurrencySpec("honor", tradeable=False)],
        items=[
            ItemSpec(
                "ore", "gold", max_stack=100, vendor_buy_price=12, vendor_sell_price=8
            ),
            ItemSpec("sword", "gold", max_stack=1),
            ItemSpec("herb", "gold", max_stack=50),
            ItemSpec("badge", "honor", max_stack=1, tradeable=False),
        ],
        faucets=[
            FaucetSpec("daily", "gold", amount=10_000),
            FaucetSpec("arena", "honor", amount=5),
        ],
        sinks=[
            SinkSpec("market_listing", "gold", flat=1, bps=listing_bps),
            SinkSpec("market_sales_tax", "gold", bps=tax_bps),
            SinkSpec("repair", "gold", flat=5),
        ],
        default_slots=slots,
        item_weights={"ore": 1, "sword": 10, "herb": 0},
    )
    for owner in owners:
        econ.open_account(owner)
    return econ


def config(**kw) -> MarketConfig:
    base = dict(
        currency="gold",
        listing_sink="market_listing",
        sales_tax_sink="market_sales_tax",
        period_ticks=100,
        basket=(("ore", 10), ("herb", 5)),
    )
    base.update(kw)
    return MarketConfig(**base)


def build_market(
    owners=OWNERS, *, econ_kw=None, serialized=("sword",), refs=None, **kw
) -> PlayerMarket:
    econ = build_econ(owners, **(econ_kw or {}))
    refs = {"herb": 20, "sword": 500} if refs is None else refs
    return PlayerMarket(
        econ, config(**kw), serialized=serialized, reference_prices=refs
    )


def funded(**kw) -> PlayerMarket:
    """Market where every owner has 10k gold and 50 ore, 30 herb."""
    market = build_market(**kw)
    econ = market.econ
    for owner in kw.get("owners", OWNERS):
        econ.grant("daily", owner, tick=0)
        econ.grant_items("mine", owner, "ore", 50)
        econ.grant_items("garden", owner, "herb", 30)
    return market


@pytest.fixture
def market() -> PlayerMarket:
    return funded()

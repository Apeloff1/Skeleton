"""Shared fixtures for the industry tests."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.core import GameplayEconomy
from skeleton.economy.gameplay.industry.blueprints import Blueprint
from skeleton.economy.gameplay.industry.engine import IndustryConfig, IndustrySystem
from skeleton.economy.gameplay.industry.extraction import NodeSpec
from skeleton.economy.gameplay.industry.research import ResearchCurve
from skeleton.economy.gameplay.market.exchange import MarketConfig, PlayerMarket
from skeleton.simulation.economy.sim import CurrencySpec, FaucetSpec, ItemSpec, SinkSpec

OWNERS = ("ana", "bo")


def build_econ(owners=OWNERS, *, slots: int = 16) -> GameplayEconomy:
    econ = GameplayEconomy(
        currencies=[CurrencySpec("gold")],
        items=[
            ItemSpec(
                "ore", "gold", max_stack=1_000, vendor_buy_price=12, vendor_sell_price=8
            ),
            ItemSpec("coal", "gold", max_stack=1_000),
            ItemSpec("ingot", "gold", max_stack=500),
            ItemSpec("plate", "gold", max_stack=200),
            ItemSpec("hull", "gold", max_stack=10),
        ],
        faucets=[FaucetSpec("daily", "gold", amount=10_000)],
        sinks=[
            SinkSpec("industry_install", "gold", flat=2, bps=100),
            SinkSpec("industry_research", "gold", flat=1),
            SinkSpec("market_listing", "gold", flat=1, bps=100),
            SinkSpec("market_sales_tax", "gold", bps=500),
        ],
        default_slots=slots,
    )
    for owner in owners:
        econ.open_account(owner)
    return econ


BLUEPRINTS = (
    Blueprint(
        "smelt_ingot",
        "ingot",
        1,
        (("ore", 3), ("coal", 1)),
        base_ticks=10,
        waste_bps=1_000,
    ),
    Blueprint("press_plate", "plate", 2, (("ingot", 3),), base_ticks=20, waste_bps=500),
    Blueprint("weld_hull", "hull", 1, (("plate", 4), ("ingot", 2)), base_ticks=50),
)

NODES = (
    NodeSpec(
        "vein_a",
        "ore",
        reserve=100,
        yield_per_cycle=20,
        cycle_ticks=5,
        window_ticks=10,
        window_cap=30,
    ),
    NodeSpec("seam_b", "coal", reserve=40, yield_per_cycle=10, cycle_ticks=1),
)


def config(**kw) -> IndustryConfig:
    base = dict(
        currency="gold",
        install_sink="industry_install",
        research_sink="industry_research",
        period_ticks=100,
        research_curve=ResearchCurve(base_cost=100, base_ticks=30),
    )
    base.update(kw)
    return IndustryConfig(**base)


def build_system(*, market: bool = False, econ=None, **kw) -> IndustrySystem:
    econ = econ or build_econ()
    mkt = None
    if market:
        mkt = PlayerMarket(
            econ,
            MarketConfig(
                currency="gold",
                listing_sink="market_listing",
                sales_tax_sink="market_sales_tax",
                period_ticks=100,
                basket=(("ingot", 1),),
            ),
            reference_prices={"ingot": 50, "plate": 160, "hull": 1_000},
        )
    return IndustrySystem(econ, config(**kw), BLUEPRINTS, NODES, market=mkt)


def stocked(**kw) -> IndustrySystem:
    """Everyone has 10k gold, 300 ore and 100 coal (granted, not extracted)."""
    system = build_system(**kw)
    for owner in OWNERS:
        system.econ.grant("daily", owner, tick=0)
        system.econ.grant_items("stockpile", owner, "ore", 300)
        system.econ.grant_items("stockpile", owner, "coal", 100)
    return system


@pytest.fixture
def system() -> IndustrySystem:
    return stocked()

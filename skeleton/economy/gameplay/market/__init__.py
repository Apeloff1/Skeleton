"""Player market for the gameplay economy (#807, B029 follow-on).

A deterministic, integer-money exchange layered on
:class:`~skeleton.economy.gameplay.core.GameplayEconomy`:

* :mod:`.book` — price-time-priority order book (sell offers, buy requests).
* :mod:`.exchange` — :class:`PlayerMarket`: escrow, matching, settlement,
  listing fees and sales taxes burned through declared economy sinks.
* :mod:`.history` — OHLC and volume per period.
* :mod:`.integrity` — wash trading, spoofing, out-of-band prints and
  duplicated-item detection.
* :mod:`.telemetry` — money supply, market velocity and a price index.
* :mod:`.save_section` — market state as its own ``GameSavePlane`` section.
* :mod:`.replay` — command logs and replay-determinism fingerprints.

Network sync and UI are owned elsewhere and deliberately absent.
"""

from skeleton.economy.gameplay.market.book import BUY, SELL, Order, OrderBook
from skeleton.economy.gameplay.market.errors import MarketError
from skeleton.economy.gameplay.market.exchange import (
    ESCROW_OWNER,
    MarketConfig,
    PlayerMarket,
)

__all__ = [
    "BUY",
    "ESCROW_OWNER",
    "SELL",
    "MarketConfig",
    "MarketError",
    "Order",
    "OrderBook",
    "PlayerMarket",
]

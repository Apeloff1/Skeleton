"""Inflation telemetry for the player market.

Per period (same ``period_ticks`` as :class:`PriceHistory`) the market
records an integer snapshot:

* **Money supply** — circulating supply of the currency (minted - burned)
  from the economy ledger, split into player-held and escrowed.
* **Velocity** — market notional settled in the period divided by money
  supply, in basis points (``turnover * 10_000 // supply``).
* **Price index** — fixed-basket (Laspeyres) index in basis points:
  ``sum(w_i * p_i,t) * 10_000 // sum(w_i * p_i,0)``. Base prices are the
  first observed VWAP per basket item; missing prices carry forward.
* **Sinks** — listing fees and sales tax burned in the period.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from skeleton.economy.gameplay.market.errors import MarketError
from skeleton.simulation.economy.sim import BPS, _req_int


@dataclass
class PeriodStats:
    period: int
    turnover: int = 0
    fills: int = 0
    listing_fees: int = 0
    sales_tax: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "period": self.period,
            "turnover": self.turnover,
            "fills": self.fills,
            "listing_fees": self.listing_fees,
            "sales_tax": self.sales_tax,
        }


@dataclass
class InflationTelemetry:
    currency: str
    basket: Mapping[str, int] = field(default_factory=dict)
    _current: PeriodStats | None = None
    _base_prices: dict[str, int] = field(default_factory=dict)
    _last_prices: dict[str, int] = field(default_factory=dict)
    rows: list[dict[str, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.basket = {
            k: _req_int(v, "basket weight", minimum=1)
            for k, v in sorted(dict(self.basket).items())
        }

    def _stats(self, period: int) -> PeriodStats:
        if self._current is None:
            self._current = PeriodStats(period)
        elif period < self._current.period:
            raise MarketError("telemetry period went backwards")
        return self._current

    def on_fill(
        self, period: int, item_id: str, unit_price: int, qty: int, tax: int
    ) -> None:
        stats = self._stats(period)
        if period != stats.period:
            raise MarketError("close the open period before recording the next")
        stats.turnover += unit_price * qty
        stats.fills += 1
        stats.sales_tax += tax
        if item_id in self.basket:
            self._last_prices[item_id] = unit_price

    def on_fee(self, period: int, fee: int) -> None:
        stats = self._stats(period)
        if period != stats.period:
            raise MarketError("close the open period before recording the next")
        stats.listing_fees += fee

    def pending_period(self) -> int | None:
        return None if self._current is None else self._current.period

    def price_index(self) -> int | None:
        """Basket index in bps, or ``None`` until every basket item has a base price."""
        if not self.basket or any(i not in self._base_prices for i in self.basket):
            return None
        base = sum(w * self._base_prices[i] for i, w in self.basket.items())
        now = sum(
            w * self._last_prices.get(i, self._base_prices[i])
            for i, w in self.basket.items()
        )
        return now * BPS // base if base else None

    def close(
        self, period: int, supply: int, escrowed: int, vwaps: Mapping[str, int | None]
    ) -> dict[str, int]:
        """Close ``period``: fold VWAPs into the index and emit one row."""
        stats = (
            self._current
            if self._current is not None and self._current.period == period
            else PeriodStats(period)
        )
        if self.rows and period <= self.rows[-1]["period"]:
            raise MarketError("period already closed")
        for item_id in self.basket:
            v = vwaps.get(item_id)
            if v is not None:
                self._last_prices[item_id] = v
                self._base_prices.setdefault(item_id, v)
        index = self.price_index()
        row = stats.to_dict()
        row.update(
            {
                "money_supply": supply,
                "escrowed": escrowed,
                "player_held": supply - escrowed,
                "velocity_bps": stats.turnover * BPS // supply if supply > 0 else 0,
                "price_index_bps": -1 if index is None else index,
                "sinks": stats.listing_fees + stats.sales_tax,
            }
        )
        self.rows.append(row)
        self._current = None
        return dict(row)

    def inflation_bps(self, lookback: int = 1) -> int | None:
        """Change of the price index over ``lookback`` closed periods, in bps."""
        _req_int(lookback, "lookback", minimum=1)
        valid = [r for r in self.rows if r["price_index_bps"] > 0]
        if len(valid) <= lookback:
            return None
        then, now = (
            valid[-1 - lookback]["price_index_bps"],
            valid[-1]["price_index_bps"],
        )
        return (now - then) * BPS // then

    def to_state(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "basket": dict(self.basket),
            "current": None if self._current is None else self._current.to_dict(),
            "base_prices": dict(sorted(self._base_prices.items())),
            "last_prices": dict(sorted(self._last_prices.items())),
            "rows": [dict(r) for r in self.rows],
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "InflationTelemetry":
        tel = cls(str(state["currency"]), dict(state["basket"]))
        cur = state.get("current")
        if cur is not None:
            tel._current = PeriodStats(**{k: int(v) for k, v in cur.items()})
        tel._base_prices = {k: int(v) for k, v in state["base_prices"].items()}
        tel._last_prices = {k: int(v) for k, v in state["last_prices"].items()}
        tel.rows = [dict(r) for r in state["rows"]]
        return tel


__all__ = ["InflationTelemetry", "PeriodStats"]

"""Price history: OHLC candles and volume per fixed tick period.

Periods are ``tick // period_ticks``. Each candle stores integer open, high,
low, close unit prices, traded quantity, notional (sum of ``qty * price``),
print count and a volume-weighted average price (floor division). Candles
are kept per item; ``retain`` bounds how many periods are kept per item.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeleton.economy.gameplay.market.errors import MarketError
from skeleton.simulation.economy.sim import _req_int

MAX_FILLED_CANDLES = 10_000


@dataclass
class Candle:
    period: int
    open: int
    high: int
    low: int
    close: int
    volume: int = 0
    notional: int = 0
    prints: int = 0

    @property
    def vwap(self) -> int:
        return self.notional // self.volume if self.volume else self.close

    def add(self, unit_price: int, qty: int) -> None:
        self.high = max(self.high, unit_price)
        self.low = min(self.low, unit_price)
        self.close = unit_price
        self.volume += qty
        self.notional += unit_price * qty
        self.prints += 1

    def to_dict(self) -> dict[str, int]:
        return {
            "period": self.period,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "notional": self.notional,
            "prints": self.prints,
            "vwap": self.vwap,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Candle":
        return cls(
            period=int(data["period"]),
            open=int(data["open"]),
            high=int(data["high"]),
            low=int(data["low"]),
            close=int(data["close"]),
            volume=int(data["volume"]),
            notional=int(data["notional"]),
            prints=int(data["prints"]),
        )


class PriceHistory:
    def __init__(self, period_ticks: int = 100, retain: int = 1_000) -> None:
        self.period_ticks = _req_int(period_ticks, "period_ticks", minimum=1)
        self.retain = _req_int(retain, "retain", minimum=1)
        self._candles: dict[str, list[Candle]] = {}
        self._last_tick = -1

    def period_of(self, tick: int) -> int:
        return _req_int(tick, "tick") // self.period_ticks

    def record(self, item_id: str, tick: int, unit_price: int, qty: int) -> Candle:
        _req_int(unit_price, "unit_price", minimum=1)
        _req_int(qty, "qty", minimum=1)
        if tick < self._last_tick:
            raise MarketError("history tick went backwards")
        self._last_tick = tick
        period = self.period_of(tick)
        candles = self._candles.setdefault(item_id, [])
        if candles and candles[-1].period == period:
            candle = candles[-1]
            candle.add(unit_price, qty)
        else:
            candle = Candle(period, unit_price, unit_price, unit_price, unit_price)
            candle.add(unit_price, qty)
            candles.append(candle)
            if len(candles) > self.retain:
                del candles[: len(candles) - self.retain]
        return candle

    def candles(
        self, item_id: str, *, since_period: int | None = None, fill_gaps: bool = False
    ) -> list[dict[str, int]]:
        """Candles for one item. ``fill_gaps`` adds flat zero-volume candles."""
        rows = self._candles.get(item_id, [])
        if since_period is not None:
            rows = [c for c in rows if c.period >= since_period]
        if not fill_gaps or not rows:
            return [c.to_dict() for c in rows]
        # Retention bounds recorded candles, not gaps between sparse periods.
        # Preflight the complete expansion before allocating any gap rows.
        count = len(rows)
        for previous, current in zip(rows, rows[1:]):
            count += max(0, current.period - previous.period - 1)
            if count > MAX_FILLED_CANDLES:
                raise MarketError("filled price history exceeds output bound")
        if count > MAX_FILLED_CANDLES:
            raise MarketError("filled price history exceeds output bound")
        out: list[dict[str, int]] = []
        prev: Candle | None = None
        for c in rows:
            if prev is not None:
                for p in range(prev.period + 1, c.period):
                    gap = Candle(p, prev.close, prev.close, prev.close, prev.close)
                    out.append(gap.to_dict())
            out.append(c.to_dict())
            prev = c
        return out

    def last_price(self, item_id: str) -> int | None:
        rows = self._candles.get(item_id)
        return rows[-1].close if rows else None

    def candle(self, item_id: str, period: int) -> dict[str, int] | None:
        for c in self._candles.get(item_id, []):
            if c.period == period:
                return c.to_dict()
        return None

    def vwap(self, item_id: str, periods: int) -> int | None:
        """VWAP over the last ``periods`` recorded candles."""
        _req_int(periods, "periods", minimum=1)
        rows = self._candles.get(item_id, [])[-periods:]
        volume = sum(c.volume for c in rows)
        return sum(c.notional for c in rows) // volume if volume else None

    def volume(self, item_id: str, period: int) -> int:
        c = self.candle(item_id, period)
        return 0 if c is None else c["volume"]

    def notional_in_period(self, period: int) -> int:
        return sum(
            c.notional
            for rows in self._candles.values()
            for c in rows
            if c.period == period
        )

    def items(self) -> list[str]:
        return sorted(self._candles)

    def to_state(self) -> dict[str, Any]:
        return {
            "period_ticks": self.period_ticks,
            "retain": self.retain,
            "last_tick": self._last_tick,
            "candles": {
                k: [c.to_dict() for c in v] for k, v in sorted(self._candles.items())
            },
        }

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "PriceHistory":
        hist = cls(int(state["period_ticks"]), int(state["retain"]))
        hist._last_tick = int(state["last_tick"])
        hist._candles = {
            k: [Candle.from_dict(c) for c in v] for k, v in state["candles"].items()
        }
        return hist


__all__ = ["Candle", "PriceHistory"]

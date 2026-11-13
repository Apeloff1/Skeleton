"""B029 market integrity guard for player-to-player trades.

:class:`MarketGuard` sits in front of :meth:`GameplayEconomy.trade` and
refuses fills that are typical of real-money trading, laundering or bot
farming rather than play:

* **Price bands.** Each item has an integer reference unit price (seeded
  from the vendor midpoint or set explicitly, then moved by an EMA of
  accepted fills). Fills whose unit price lies outside ``±band_bps`` of the
  reference are refused — a 1-copper sword or a 1M-gold arrow is a gift in
  disguise.
* **Round trips.** A fill that reverses a recent fill (same item, buyer and
  seller swapped) inside ``round_trip_ticks`` is refused; A→B→A cycles are
  how wash volume and laundering hide.
* **Velocity.** Each owner may take part in at most ``max_fills`` fills per
  ``window_ticks``.

Every refusal is recorded with its reason for moderation telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from skeleton.economy.gameplay.core import GameplayEconomy
from skeleton.simulation.economy.sim import BPS, EconomySimError, _req_int


class MarketIntegrityError(EconomySimError):
    code = "ECO.MARKET"


@dataclass(frozen=True)
class Fill:
    tick: int
    seller: str
    buyer: str
    item_id: str
    qty: int
    price: int


@dataclass
class MarketGuard:
    econ: GameplayEconomy
    band_bps: int = 3_000
    ema_bps: int = 2_000
    round_trip_ticks: int = 1_000
    max_fills: int = 20
    window_ticks: int = 100
    allow_discovery: bool = False
    _reference: dict[str, int] = field(default_factory=dict)
    _fills: list[Fill] = field(default_factory=list)
    _refusals: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        _req_int(self.band_bps, "band_bps", minimum=1)
        _req_int(self.ema_bps, "ema_bps", minimum=1)
        if self.ema_bps > BPS:
            raise MarketIntegrityError("ema_bps above 100%")
        _req_int(self.round_trip_ticks, "round_trip_ticks")
        _req_int(self.max_fills, "max_fills", minimum=1)
        _req_int(self.window_ticks, "window_ticks", minimum=1)
        for item_id, spec in self.econ.items.items():
            if spec.vendor_buy_price is not None and spec.vendor_sell_price is not None:
                self._reference[item_id] = (spec.vendor_buy_price + spec.vendor_sell_price) // 2

    def set_reference(self, item_id: str, unit_price: int) -> None:
        if item_id not in self.econ.items:
            raise MarketIntegrityError("no such item")
        self._reference[item_id] = _req_int(unit_price, "unit_price", minimum=1)

    def reference(self, item_id: str) -> int | None:
        return self._reference.get(item_id)

    def band(self, item_id: str) -> tuple[int, int] | None:
        ref = self._reference.get(item_id)
        if ref is None:
            return None
        width = ref * self.band_bps // BPS
        return max(1, ref - width), ref + width

    def _refuse(self, tick: int, reason: str, **ctx: Any) -> None:
        self._refusals.append({"tick": tick, "reason": reason, **ctx})
        raise MarketIntegrityError(reason)

    def fill(self, seller: str, buyer: str, item_id: str, qty: int, price: int, tick: int) -> dict[str, int]:
        _req_int(qty, "qty", minimum=1)
        _req_int(price, "price", minimum=1)
        _req_int(tick, "tick")
        if self._fills and tick < self._fills[-1].tick:
            raise MarketIntegrityError("tick went backwards")
        ctx = {"seller": seller, "buyer": buyer, "item": item_id, "qty": qty, "price": price}
        unit = price // qty
        bounds = self.band(item_id)
        if bounds is None and not self.allow_discovery:
            self._refuse(tick, "no reference price", **ctx)
        if bounds is not None and not bounds[0] <= unit <= bounds[1]:
            self._refuse(tick, "price outside band", **ctx)
        for f in reversed(self._fills):
            if tick - f.tick > self.round_trip_ticks:
                break
            if f.item_id == item_id and f.seller == buyer and f.buyer == seller:
                self._refuse(tick, "round-trip trade", **ctx)
        for who in (seller, buyer):
            recent = sum(
                1 for f in self._fills if tick - f.tick < self.window_ticks and who in (f.seller, f.buyer)
            )
            if recent >= self.max_fills:
                self._refuse(tick, "trade velocity exceeded", who=who, **ctx)
        result = self.econ.trade(seller, buyer, item_id, qty, price)
        ref = self._reference.get(item_id)
        self._reference[item_id] = unit if ref is None else ref + (unit - ref) * self.ema_bps // BPS
        self._fills.append(Fill(tick, seller, buyer, item_id, qty, price))
        horizon = max(self.round_trip_ticks, self.window_ticks)
        self._fills = [f for f in self._fills if tick - f.tick <= horizon]
        return result

    def refusals(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._refusals]


__all__ = ["Fill", "MarketGuard", "MarketIntegrityError"]

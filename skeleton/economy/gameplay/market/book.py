"""Deterministic price-time-priority order book.

The book is a pure data structure: it knows nothing about money or items.
:class:`~skeleton.economy.gameplay.market.exchange.PlayerMarket` owns escrow
and settlement and uses the book only to rank and look up resting orders.

Ordering rules (identical on every replay):

* Sells rank by ascending unit price, then ascending ``seq``.
* Buys rank by descending unit price, then ascending ``seq``.
* ``seq`` is a strictly increasing integer assigned by the market, so two
  orders never compare equal and ties never depend on dict or hash order.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Any, Iterator

from skeleton.economy.gameplay.market.errors import MarketError

SELL = "sell"
BUY = "buy"
SIDES = (SELL, BUY)


@dataclass
class Order:
    order_id: int
    side: str
    owner: str
    item_id: str
    qty: int
    unit_price: int
    seq: int
    tick: int
    expires_at: int | None = None
    remaining: int = -1
    serials: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise MarketError("side must be 'sell' or 'buy'")
        if self.remaining < 0:
            self.remaining = self.qty

    @property
    def filled(self) -> int:
        return self.qty - self.remaining

    def rank_key(self) -> tuple[int, int]:
        price = self.unit_price if self.side == SELL else -self.unit_price
        return (price, self.seq)

    def crosses(self, other_price: int) -> bool:
        """Would this order trade against a resting opposite order at ``other_price``?"""
        if self.side == BUY:
            return other_price <= self.unit_price
        return other_price >= self.unit_price

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "side": self.side,
            "owner": self.owner,
            "item_id": self.item_id,
            "qty": self.qty,
            "remaining": self.remaining,
            "unit_price": self.unit_price,
            "seq": self.seq,
            "tick": self.tick,
            "expires_at": self.expires_at,
            "serials": list(self.serials),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Order":
        return cls(
            order_id=int(data["order_id"]),
            side=str(data["side"]),
            owner=str(data["owner"]),
            item_id=str(data["item_id"]),
            qty=int(data["qty"]),
            unit_price=int(data["unit_price"]),
            seq=int(data["seq"]),
            tick=int(data["tick"]),
            expires_at=None
            if data.get("expires_at") is None
            else int(data["expires_at"]),
            remaining=int(data["remaining"]),
            serials=tuple(data.get("serials", ())),
        )


class _Side:
    """One side of one item's book: sorted keys plus an id index."""

    def __init__(self) -> None:
        self._keys: list[tuple[int, int]] = []
        self._by_key: dict[tuple[int, int], Order] = {}

    def __len__(self) -> int:
        return len(self._keys)

    def add(self, order: Order) -> None:
        key = order.rank_key()
        if key in self._by_key:
            raise MarketError("duplicate order sequence")
        bisect.insort(self._keys, key)
        self._by_key[key] = order

    def remove(self, order: Order) -> None:
        key = order.rank_key()
        if self._by_key.get(key) is not order:
            raise MarketError("order not resting on this side")
        idx = bisect.bisect_left(self._keys, key)
        del self._keys[idx]
        del self._by_key[key]

    def best(self) -> Order | None:
        return self._by_key[self._keys[0]] if self._keys else None

    def __iter__(self) -> Iterator[Order]:
        for key in list(self._keys):
            order = self._by_key.get(key)
            if order is not None:
                yield order


class OrderBook:
    """All resting orders, per item and side."""

    def __init__(self) -> None:
        self._books: dict[str, dict[str, _Side]] = {}
        self._orders: dict[int, Order] = {}

    def _side(self, item_id: str, side: str) -> _Side:
        sides = self._books.setdefault(item_id, {SELL: _Side(), BUY: _Side()})
        return sides[side]

    def add(self, order: Order) -> None:
        if order.order_id in self._orders:
            raise MarketError("duplicate order id")
        if order.remaining < 1:
            raise MarketError("cannot rest an empty order")
        self._side(order.item_id, order.side).add(order)
        self._orders[order.order_id] = order

    def remove(self, order_id: int) -> Order:
        order = self._orders.pop(order_id, None)
        if order is None:
            raise MarketError("no such resting order")
        self._side(order.item_id, order.side).remove(order)
        return order

    def get(self, order_id: int) -> Order | None:
        return self._orders.get(order_id)

    def __contains__(self, order_id: object) -> bool:
        return order_id in self._orders

    def __len__(self) -> int:
        return len(self._orders)

    def best(self, item_id: str, side: str) -> Order | None:
        return self._side(item_id, side).best()

    def best_price(self, item_id: str, side: str) -> int | None:
        best = self.best(item_id, side)
        return None if best is None else best.unit_price

    def spread(self, item_id: str) -> int | None:
        bid = self.best_price(item_id, BUY)
        ask = self.best_price(item_id, SELL)
        return None if bid is None or ask is None else ask - bid

    def iter_side(self, item_id: str, side: str) -> Iterator[Order]:
        """Resting orders on one side in priority order (safe to mutate during)."""
        return iter(self._side(item_id, side))

    def orders(self) -> list[Order]:
        """All resting orders sorted by ``order_id`` (deterministic)."""
        return [self._orders[k] for k in sorted(self._orders)]

    def orders_of(self, owner: str) -> list[Order]:
        return [o for o in self.orders() if o.owner == owner]

    def items(self) -> list[str]:
        return sorted(
            item
            for item, sides in self._books.items()
            if len(sides[SELL]) or len(sides[BUY])
        )

    def depth(self, item_id: str, side: str, levels: int = 5) -> list[tuple[int, int]]:
        """Aggregated ``(unit_price, qty)`` levels in priority order."""
        out: list[tuple[int, int]] = []
        for order in self.iter_side(item_id, side):
            if out and out[-1][0] == order.unit_price:
                out[-1] = (order.unit_price, out[-1][1] + order.remaining)
            elif len(out) < levels:
                out.append((order.unit_price, order.remaining))
            else:
                break
        return out

    def resting_qty(self, item_id: str, side: str) -> int:
        return sum(o.remaining for o in self.iter_side(item_id, side))

    def expired(self, tick: int) -> list[Order]:
        return [
            o
            for o in self.orders()
            if o.expires_at is not None and o.expires_at <= tick
        ]


__all__ = ["BUY", "SELL", "SIDES", "Order", "OrderBook"]

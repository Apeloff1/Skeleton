"""Order book: price-time priority, depth and deterministic ordering."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.market.book import BUY, SELL, Order, OrderBook
from skeleton.economy.gameplay.market.errors import MarketError


def _o(oid, side, price, seq=None, qty=5, owner="a", item="ore"):
    return Order(
        oid, side, owner, item, qty, price, seq if seq is not None else oid, tick=0
    )


def test_sell_side_ranks_low_price_then_time():
    book = OrderBook()
    for o in (_o(1, SELL, 12), _o(2, SELL, 10), _o(3, SELL, 10), _o(4, SELL, 11)):
        book.add(o)
    assert [o.order_id for o in book.iter_side("ore", SELL)] == [2, 3, 4, 1]
    assert book.best_price("ore", SELL) == 10


def test_buy_side_ranks_high_price_then_time():
    book = OrderBook()
    for o in (_o(1, BUY, 9), _o(2, BUY, 11), _o(3, BUY, 11), _o(4, BUY, 10)):
        book.add(o)
    assert [o.order_id for o in book.iter_side("ore", BUY)] == [2, 3, 4, 1]


def test_spread_depth_and_resting_qty():
    book = OrderBook()
    book.add(_o(1, BUY, 9, qty=3))
    book.add(_o(2, BUY, 9, qty=4))
    book.add(_o(3, BUY, 8, qty=1))
    book.add(_o(4, SELL, 12, qty=2))
    assert book.spread("ore") == 3
    assert book.depth("ore", BUY) == [(9, 7), (8, 1)]
    assert book.depth("ore", BUY, levels=1) == [(9, 7)]
    assert book.resting_qty("ore", BUY) == 8
    assert book.spread("herb") is None


def test_remove_and_duplicates():
    book = OrderBook()
    book.add(_o(1, SELL, 10))
    with pytest.raises(MarketError):
        book.add(_o(1, SELL, 11, seq=9))
    with pytest.raises(MarketError):
        book.add(_o(2, SELL, 10, seq=1))
    assert book.remove(1).order_id == 1
    assert len(book) == 0 and book.best("ore", SELL) is None
    with pytest.raises(MarketError):
        book.remove(1)


def test_iteration_tolerates_removal_and_expiry_listing():
    book = OrderBook()
    for i in range(1, 6):
        o = _o(i, SELL, 10 + i)
        o.expires_at = 10 * i
        book.add(o)
    seen = []
    for o in book.iter_side("ore", SELL):
        seen.append(o.order_id)
        book.remove(o.order_id)
    assert seen == [1, 2, 3, 4, 5]
    for i in range(1, 4):
        o = _o(i, BUY, 5)
        o.expires_at = 10 * i
        book.add(o)
    assert [o.order_id for o in book.expired(20)] == [1, 2]


def test_order_round_trip_and_validation():
    o = _o(7, BUY, 13)
    o.serials = ()
    assert Order.from_dict(o.to_dict()) == o
    assert o.crosses(13) and o.crosses(12) and not o.crosses(14)
    s = _o(8, SELL, 13)
    assert s.crosses(13) and s.crosses(14) and not s.crosses(12)
    with pytest.raises(MarketError):
        _o(9, "hold", 1)


def test_items_lists_only_nonempty_books():
    book = OrderBook()
    book.add(_o(1, SELL, 10, item="herb"))
    book.add(_o(2, SELL, 10, item="ore"))
    book.remove(2)
    assert book.items() == ["herb"]
    assert [o.order_id for o in book.orders_of("a")] == [1]

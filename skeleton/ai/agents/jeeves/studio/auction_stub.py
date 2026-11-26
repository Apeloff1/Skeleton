"""Auction stub. Pointer for rare item bidding."""
from typing import Any, Dict


class AuctionStub:
    def __init__(self) -> None:
        self.lots: Dict[str, Dict[str, Any]] = {}

    def list(self, item: str, start: int) -> Dict[str, Any]:
        if not isinstance(item, str) or not item.strip():
            return {"ok": False, "reason": "empty_item"}
        if isinstance(start, bool) or not isinstance(start, int) or start < 0:
            return {"ok": False, "reason": "negative_start"}
        if item in self.lots:
            return {"ok": False, "reason": "duplicate_lot"}
        self.lots[item] = {"item": item, "price": start, "bidder": None, "closed": False, "active": True}
        return {"ok": True, "item": item, "start": start, "price": start, "active": True, "reason": "ok"}

    def bid(self, item: str, amount: int, bidder: str) -> Dict[str, Any]:
        lot = self.lots.get(item) if isinstance(item, str) else None
        if lot is None:
            return {"ok": False, "reason": "unknown_lot"}
        if lot["closed"]:
            return {"ok": False, "reason": "closed", "bidder": lot["bidder"]}
        if not isinstance(bidder, str) or not bidder.strip():
            return {"ok": False, "reason": "missing_bidder"}
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= lot["price"]:
            return {"ok": False, "reason": "bid_too_low", "price": lot["price"]}
        lot["price"] = amount
        lot["bidder"] = bidder
        return {"ok": True, "item": item, "price": amount, "bidder": bidder, "reason": "ok"}

    def close(self, item: str) -> Dict[str, Any]:
        lot = self.lots.get(item) if isinstance(item, str) else None
        if lot is None:
            return {"ok": False, "reason": "unknown_lot"}
        lot["closed"] = True
        lot["active"] = False
        return {"ok": True, "item": item, "bidder": lot["bidder"], "price": lot["price"], "closed": True, "reason": "ok"}

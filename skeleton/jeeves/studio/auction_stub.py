"""Auction stub. Pointer for rare item bidding."""
from typing import Any, Dict
class AuctionStub:
    def list(self, item: str, start: int) -> Dict[str, Any]:
        return {"item": item, "start": start, "active": True}

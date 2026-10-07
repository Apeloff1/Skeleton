"""Vickrey auction resource allocation (split from swarm_types.py, v16.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from skeleton.kernel.ids import AgentId

from .types import AgentState, CapabilityVector

# =============================================================================
# RESOURCE AUCTIONING (VICKREY / SECOND-PRICE SEALED BID)
# =============================================================================

@dataclass
class AuctionBid:
    """A sealed bid in a Vickrey auction."""
    agent_id: AgentId
    value: float           # Bid value (willingness to pay / capacity)
    cost: float            # True cost (private information)
    capability_match: float = 0.0  # How well capabilities match the task


class VickreyAuction:
    """
    Second-price sealed-bid auction for resource allocation.
    Winner pays the second-highest bid (incentive-compatible).
    """

    def __init__(self) -> None:
        self._history: List[Dict[str, Any]] = []

    def run(
        self,
        task_requirements: CapabilityVector,
        bidders: List[AgentState],
    ) -> Tuple[Optional[AgentState], float, List[Dict[str, Any]]]:
        """Run auction. Returns (winner, price_paid, auction_record)."""
        if not bidders:
            return None, 0.0, []

        bids: List[AuctionBid] = []
        for bidder in bidders:
            if not bidder.is_alive():
                continue
            match = bidder.capabilities.similarity(task_requirements)
            value = bidder.effective_capacity() * match
            cost = bidder.load_factor * 10.0
            bids.append(AuctionBid(
                agent_id=bidder.agent_id,
                value=value,
                cost=cost,
                capability_match=match,
            ))

        if not bids:
            return None, 0.0, []

        bids.sort(key=lambda b: b.value, reverse=True)
        winner_bid = bids[0]
        second_price = bids[1].value if len(bids) > 1 else 0.0

        winner = next(
            (b for b in bidders if b.agent_id == winner_bid.agent_id), None
        )

        record = {
            "winner": str(winner_bid.agent_id),
            "winning_bid": winner_bid.value,
            "price_paid": second_price,
            "capability_match": winner_bid.capability_match,
            "total_bidders": len(bids),
            "all_bids": [
                {"agent_id": str(b.agent_id), "value": b.value, "cost": b.cost, "match": b.capability_match}
                for b in bids
            ],
        }
        self._history.append(record)

        return winner, second_price, [record]

"""Vickrey auction resource allocation (split from swarm_types.py, v16.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .types import AgentState, CapabilityVector


class AuctionError(ValueError):
    """A sealed bid cannot be priced."""

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
        bids: Optional[Mapping[str, float]] = None,
    ) -> Tuple[Optional[AgentState], float, List[Dict[str, Any]]]:
        """Price an explicit sealed bid. The auction does not invent one."""
        if not isinstance(task_requirements, CapabilityVector):
            raise AuctionError("task requirements are required")
        if not isinstance(bids, Mapping) or len(bids) < 2:
            raise AuctionError("a second-price auction needs at least two sealed bids")
        live = {str(bidder.agent_id): bidder for bidder in bidders if bidder.is_alive()}
        if len(live) != len([bidder for bidder in bidders if bidder.is_alive()]):
            raise AuctionError("duplicate bidder")
        sealed: List[AuctionBid] = []
        for agent_id, value in bids.items():
            if not isinstance(agent_id, str) or agent_id not in live:
                raise AuctionError("bid is not from a live bidder")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
                raise AuctionError("bid must be positive")
            bidder = live[agent_id]
            sealed.append(AuctionBid(
                agent_id=bidder.agent_id,
                value=float(value),
                cost=float(value),
                capability_match=bidder.capabilities.similarity(task_requirements),
            ))
        if len(sealed) < 2:
            raise AuctionError("a second-price auction needs at least two sealed bids")
        sealed.sort(key=lambda bid: (-bid.value, str(bid.agent_id)))
        bids = sealed
        winner_bid = bids[0]
        second_price = bids[1].value

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

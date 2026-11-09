"""The auction does not invent a bid, and a poisoned note cannot be released."""

import pytest

from skeleton.kernel.ids import AgentId
from skeleton.swarm.auction import AuctionError, VickreyAuction
from skeleton.swarm.blackboard import Blackboard
from skeleton.swarm.types import AgentRole, AgentState, CapabilityVector


def _bidder(name: str) -> AgentState:
    return AgentState(agent_id=AgentId(name), role=AgentRole.WORKER, capabilities=CapabilityVector(compute=1))


def test_second_price_uses_the_sealed_bids_only() -> None:
    auction = VickreyAuction()
    bidders = [_bidder("ada"), _bidder("bea")]
    with pytest.raises(AuctionError):
        auction.run(CapabilityVector(compute=1), bidders)
    winner, price, records = auction.run(
        CapabilityVector(compute=1),
        bidders,
        {"ada": 10, "bea": 7},
    )
    assert str(winner.agent_id) == "ada"
    assert price == 7
    assert records[0]["winning_bid"] == 10
    tied = [_bidder("ada"), _bidder("bea")]
    winner, price, _ = auction.run(CapabilityVector(compute=1), tied, {"ada": 5, "bea": 5})
    assert str(winner.agent_id) == "ada"
    assert price == 5


def test_a_poisoned_blackboard_entry_stays_off_the_live_board() -> None:
    board = Blackboard(clock=lambda: 1_000.0, blocked_producers=frozenset({"mallory"}))
    with pytest.raises(ValueError):
        board.post("swarm.bid", {"n": 1}, producer="ada", confidence=5)
    hidden = board.post("swarm.bid", {"n": 1}, producer="mallory", confidence=0.9)
    assert hidden.quarantined is True
    assert board.read("swarm.*") == []
    with pytest.raises(ValueError):
        board.release(hidden.entry_id)
    assert board.read() == []
    visible = board.post("swarm.bid", {"n": 2}, producer="ada", confidence=0.9)
    assert [item.entry_id for item in board.read("swarm.*")] == [visible.entry_id]
    assert board.read("swarmX") == []

"""
Skeleton Galaxy — Distributed consensus over live transport

Extends the federation layer so proposals and votes travel the wire:

    Node A proposes → broadcast via NodeTransport → peers vote →
    votes return → proposer tallies → consensus reached → all nodes
    notified of the outcome

The Raft-lite shape: single proposer, simple majority, no log
replication — enough for config changes, era switches, and leader
acknowledgement between a handful of skeleton nodes.

Provides:
- ConsensusEngine: proposal/vote lifecycle bound to a GalaxyNode + transport
- Proposal: tracked proposal with votes and outcome
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Proposal:
    """A tracked consensus proposal."""
    proposal_id: str
    topic: str
    value: Any
    proposer: str
    created_at: float = field(default_factory=time.time)
    votes: Dict[str, bool] = field(default_factory=dict)  # node_id -> accept
    status: str = "open"  # open | accepted | rejected

    def tally(self, electorate: int) -> Optional[str]:
        """Resolve once a majority of the electorate has voted."""
        if electorate < 1:
            return None
        needed = (electorate // 2) + 1
        yes = sum(1 for v in self.votes.values() if v)
        no = len(self.votes) - yes
        if yes >= needed:
            self.status = "accepted"
        elif no >= needed:
            self.status = "rejected"
        return self.status if self.status != "open" else None


class ConsensusEngine:
    """Proposal/vote lifecycle over NodeTransport.

    Message types on the wire:
    - consensus.propose  {proposal_id, topic, value, proposer}
    - consensus.vote     {proposal_id, voter, accept}
    - consensus.outcome  {proposal_id, status}
    """

    def __init__(self, node: Any, transport: Any, auto_accept: bool = True, bus: Optional[Any] = None):
        self._node = node
        self._transport = transport
        self._auto_accept = auto_accept
        self._bus = bus
        self._proposals: Dict[str, Proposal] = {}
        self._voters: List[Callable[[str, Any], bool]] = []  # local vote policy
        self._stats = {"proposed": 0, "votes_cast": 0, "accepted": 0, "rejected": 0}

        transport.on("consensus.propose", self._on_propose)
        transport.on("consensus.vote", self._on_vote)
        transport.on("consensus.outcome", self._on_outcome)

    def add_voter(self, fn: Callable[[str, Any], bool]) -> None:
        """Register a local policy voter: fn(topic, value) -> accept?."""
        self._voters.append(fn)

    def _electorate(self) -> int:
        """Live nodes including self."""
        alive = len(self._node._registry.discover())
        return max(1, alive + 1)

    def propose(self, topic: str, value: Any, wait: bool = False, timeout: float = 5.0) -> Proposal:
        """Propose a value; broadcast to all known peers."""
        proposal = Proposal(
            proposal_id=str(uuid.uuid4())[:10],
            topic=topic,
            value=value,
            proposer=self._node.node_id,
        )
        # Proposer votes for its own proposal
        proposal.votes[self._node.node_id] = True
        self._proposals[proposal.proposal_id] = proposal
        self._stats["proposed"] += 1

        for peer in self._node._registry.discover():
            self._transport.send(peer.address, {
                "type": "consensus.propose",
                "proposal_id": proposal.proposal_id,
                "topic": topic,
                "value": value,
                "proposer": self._node.node_id,
            })

        # Single-node electorate resolves immediately
        self._resolve(proposal)

        if wait:
            deadline = time.time() + timeout
            while proposal.status == "open" and time.time() < deadline:
                time.sleep(0.05)

        return proposal

    def _resolve(self, proposal: Proposal) -> None:
        outcome = proposal.tally(self._electorate())
        if outcome is None:
            return
        self._stats[outcome] += 1
        if self._bus:
            self._bus.emit("galaxy.consensus.resolved", {
                "proposal_id": proposal.proposal_id,
                "topic": proposal.topic,
                "status": outcome,
                "votes": dict(proposal.votes),
            })
        # Notify peers of the outcome
        for peer in self._node._registry.discover():
            self._transport.send(peer.address, {
                "type": "consensus.outcome",
                "proposal_id": proposal.proposal_id,
                "status": outcome,
            })

    # --- Wire handlers --------------------------------------------------

    def _on_propose(self, payload: Dict[str, Any]) -> None:
        """A peer proposed something: apply local policy and vote back."""
        proposal_id = payload["proposal_id"]
        topic = payload["topic"]
        value = payload["value"]
        proposer = payload["proposer"]

        # Track the proposal locally
        if proposal_id not in self._proposals:
            self._proposals[proposal_id] = Proposal(
                proposal_id=proposal_id, topic=topic, value=value, proposer=proposer,
            )

        # Vote: policy voters must all accept (and auto_accept must be on)
        accept = self._auto_accept and all(fn(topic, value) for fn in self._voters)
        self._stats["votes_cast"] += 1

        # Send the vote directly back to the proposer
        proposer_node = self._node._registry._nodes.get(proposer)
        if proposer_node is not None:
            self._transport.send(proposer_node.address, {
                "type": "consensus.vote",
                "proposal_id": proposal_id,
                "voter": self._node.node_id,
                "accept": accept,
            })

    def _on_vote(self, payload: Dict[str, Any]) -> None:
        """A vote arrived for one of our proposals."""
        proposal = self._proposals.get(payload["proposal_id"])
        if proposal is None or proposal.proposer != self._node.node_id:
            return
        proposal.votes[payload["voter"]] = bool(payload["accept"])
        self._resolve(proposal)

    def _on_outcome(self, payload: Dict[str, Any]) -> None:
        """Proposer broadcast the final outcome; record it locally."""
        proposal = self._proposals.get(payload["proposal_id"])
        if proposal is not None and proposal.status == "open":
            proposal.status = payload["status"]

    def proposals(self, status: Optional[str] = None) -> List[Proposal]:
        out = list(self._proposals.values())
        return [p for p in out if p.status == status] if status else out

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "tracked": len(self._proposals)}

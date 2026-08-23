"""
================================================================================
skeleton.swarm — Swarm Intelligence Mesh (Part 1: Types, Consensus, Auction)
================================================================================
Quad-system swarm substrate with:
  1. Consensus protocols: Raft-like leader election + Byzantine fault tolerance
  2. Specialised agent platoons: Scout, Worker, Guardian, Oracle
  3. Dynamic capability negotiation and resource auctioning
  4. Self-healing mesh topology with circuit breakers and chaos engineering
================================================================================
"""
from __future__ import annotations

import hashlib
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from skeleton.kernel.errors import AgentError, ConsensusError, AgentNotFoundError, AgentQuarantinedError
from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.kernel.ids import AgentId


# =============================================================================
# AGENT ROLES AND CAPABILITY VECTORS
# =============================================================================

class AgentRole(Enum):
    SCOUT = auto()      # Discovery, reconnaissance, information gathering
    WORKER = auto()     # Execution, computation, task completion
    GUARDIAN = auto()   # Security, validation, fault detection
    ORACLE = auto()     # Prediction, estimation, advisory


@dataclass
class CapabilityVector:
    """Multi-dimensional capability scoring for agent specialisation."""
    compute: float = 0.0        # Raw computation power
    memory: float = 0.0         # Memory capacity / recall precision
    network: float = 0.0       # Communication bandwidth / latency
    security: float = 0.0      # Validation / cryptographic strength
    prediction: float = 0.0    # Forecasting / estimation accuracy
    creativity: float = 0.0    # Generative / novel solution capacity

    def dot(self, other: "CapabilityVector") -> float:
        return (
            self.compute * other.compute +
            self.memory * other.memory +
            self.network * other.network +
            self.security * other.security +
            self.prediction * other.prediction +
            self.creativity * other.creativity
        )

    def magnitude(self) -> float:
        return (self.compute**2 + self.memory**2 + self.network**2 +
                self.security**2 + self.prediction**2 + self.creativity**2) ** 0.5

    def similarity(self, other: "CapabilityVector") -> float:
        mag = self.magnitude() * other.magnitude()
        return self.dot(other) / mag if mag > 0 else 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "compute": self.compute,
            "memory": self.memory,
            "network": self.network,
            "security": self.security,
            "prediction": self.prediction,
            "creativity": self.creativity,
        }


# =============================================================================
# AGENT STATE
# =============================================================================

class AgentStatus(Enum):
    HEALTHY = auto()
    BUSY = auto()
    QUARANTINED = auto()
    FAILED = auto()
    RECOVERING = auto()


@dataclass
class AgentState:
    """Complete state of a swarm agent."""
    agent_id: AgentId
    role: AgentRole
    capabilities: CapabilityVector
    status: AgentStatus = AgentStatus.HEALTHY
    health_score: float = 1.0          # 0.0 - 1.0
    reputation: float = 1.0            # Cumulative trust score
    load_factor: float = 0.0         # 0.0 - 1.0 (current utilisation)
    last_heartbeat: float = field(default_factory=time.time)
    heartbeat_interval: float = 5.0   # seconds
    consecutive_failures: int = 0
    max_failures: int = 3
    tasks_completed: int = 0
    tasks_failed: int = 0
    latency_ms: float = 0.0
    peers: Set[AgentId] = field(default_factory=set)
    assigned_capabilities: Set[str] = field(default_factory=set)

    def is_alive(self, now: Optional[float] = None) -> bool:
        now = now or time.time()
        return (
            self.status not in (AgentStatus.FAILED, AgentStatus.QUARANTINED)
            and (now - self.last_heartbeat) < self.heartbeat_interval * 3
        )

    def update_reputation(self, success: bool, weight: float = 1.0) -> None:
        """Update reputation using exponential moving average."""
        alpha = 0.1 * weight
        if success:
            self.reputation = (1 - alpha) * self.reputation + alpha * 1.0
            self.tasks_completed += 1
        else:
            self.reputation = (1 - alpha) * self.reputation + alpha * 0.0
            self.tasks_failed += 1
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.max_failures:
                self.status = AgentStatus.QUARANTINED
        if success:
            self.consecutive_failures = 0

    def effective_capacity(self) -> float:
        """Effective capacity = capability magnitude * health * (1 - load)."""
        return self.capabilities.magnitude() * self.health_score * (1.0 - self.load_factor)


# =============================================================================
# CONSENSUS PROTOCOLS
# =============================================================================

class ConsensusProtocol(ABC):
    """Base for consensus algorithms."""

    @abstractmethod
    def propose(
        self,
        proposal: Any,
        voters: List[AgentState],
        *,
        quorum_size: Optional[int] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """Run consensus. Returns (accepted, ballot_record)."""
        ...


class SimpleMajorityConsensus(ConsensusProtocol):
    """
    Simple majority vote with weighted reputation.
    Requires >50% of weighted votes.
    """

    def propose(
        self,
        proposal: Any,
        voters: List[AgentState],
        *,
        quorum_size: Optional[int] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        if not voters:
            raise ConsensusError("No voters available", ballot={})

        votes: Dict[str, float] = {"yes": 0.0, "no": 0.0, "abstain": 0.0}
        ballot_details: List[Dict[str, Any]] = []

        for voter in voters:
            if not voter.is_alive():
                continue
            weight = voter.reputation * voter.effective_capacity()
            vote_prob = 0.5 + 0.5 * (voter.capabilities.prediction / 10.0)
            vote = "yes" if random.random() < vote_prob else "no"
            votes[vote] += weight
            ballot_details.append({
                "agent_id": str(voter.agent_id),
                "vote": vote,
                "weight": weight,
                "reputation": voter.reputation,
            })

        total_weight = sum(votes.values())
        if total_weight == 0:
            raise ConsensusError("All voters dead or quarantined", ballot={"details": ballot_details})

        threshold = quorum_size or (total_weight / 2.0)
        accepted = votes["yes"] > threshold

        ballot = {
            "proposal_hash": hashlib.sha256(str(proposal).encode()).hexdigest()[:16],
            "total_voters": len(voters),
            "alive_voters": len([v for v in voters if v.is_alive()]),
            "votes": votes,
            "threshold": threshold,
            "accepted": accepted,
            "details": ballot_details,
        }

        if not accepted:
            raise ConsensusError(
                f"Proposal rejected: {votes['yes']:.2f} yes vs {threshold:.2f} threshold",
                ballot=ballot,
            )

        return accepted, ballot


class ByzantineFaultTolerantConsensus(ConsensusProtocol):
    """
    Byzantine fault-tolerant consensus using PBFT-inspired approach.
    Tolerates f faulty nodes among 3f+1 total nodes.
    """

    def __init__(self, f: int = 1) -> None:
        self.f = f
        self.required_nodes = 3 * f + 1

    def _commit(self, value: Any, agent_id: AgentId) -> str:
        data = f"{value}:{agent_id}:{time.time()}"
        return hashlib.sha256(data.encode()).hexdigest()

    def propose(
        self,
        proposal: Any,
        voters: List[AgentState],
        *,
        quorum_size: Optional[int] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        n = len(voters)
        if n < self.required_nodes:
            raise ConsensusError(
                f"Insufficient nodes for BFT: {n} < {self.required_nodes} (f={self.f})",
                ballot={"required": self.required_nodes, "actual": n},
            )

        proposal_hash = self._commit(proposal, AgentId.generate())

        pre_prepare_votes: Dict[str, List[str]] = {"accept": [], "reject": []}
        for voter in voters:
            if not voter.is_alive():
                continue
            is_byzantine = random.random() < 0.1
            if is_byzantine:
                vote = "reject" if random.random() < 0.5 else "accept"
            else:
                vote = "accept"
            pre_prepare_votes[vote].append(str(voter.agent_id))

        if len(pre_prepare_votes["accept"]) < 2 * self.f + 1:
            raise ConsensusError(
                "PRE-PREPARE phase failed: insufficient accepts",
                ballot={
                    "phase": "pre_prepare",
                    "accepts": len(pre_prepare_votes["accept"]),
                    "required": 2 * self.f + 1,
                },
            )

        prepare_votes: Dict[str, List[str]] = {"accept": [], "reject": []}
        for voter in voters:
            if not voter.is_alive():
                continue
            if str(voter.agent_id) in pre_prepare_votes["accept"]:
                prepare_votes["accept"].append(str(voter.agent_id))
            else:
                prepare_votes["reject"].append(str(voter.agent_id))

        if len(prepare_votes["accept"]) < 2 * self.f + 1:
            raise ConsensusError(
                "PREPARE phase failed: insufficient prepares",
                ballot={
                    "phase": "prepare",
                    "accepts": len(prepare_votes["accept"]),
                    "required": 2 * self.f + 1,
                },
            )

        commit_votes: Dict[str, List[str]] = {"accept": [], "reject": []}
        for voter in voters:
            if not voter.is_alive():
                continue
            if str(voter.agent_id) in prepare_votes["accept"]:
                commit_votes["accept"].append(str(voter.agent_id))
            else:
                commit_votes["reject"].append(str(voter.agent_id))

        accepted = len(commit_votes["accept"]) >= 2 * self.f + 1

        ballot = {
            "protocol": "pbft_inspired",
            "f": self.f,
            "total_nodes": n,
            "alive_nodes": len([v for v in voters if v.is_alive()]),
            "pre_prepare": pre_prepare_votes,
            "prepare": prepare_votes,
            "commit": commit_votes,
            "accepted": accepted,
            "proposal_hash": proposal_hash,
        }

        if not accepted:
            raise ConsensusError(
                f"COMMIT phase failed: {len(commit_votes['accept'])} < {2 * self.f + 1}",
                ballot=ballot,
            )

        return accepted, ballot


# =============================================================================
# RESOURCE AUCTIONING (VICKREY / SECOND-PRICE SEALED BID)
# =============================================================================

@dataclass
class AuctionBid:
    """A sealed bid in a Vickrey auction."""
    agent_id: AgentId
    value: float
    cost: float
    capability_match: float = 0.0


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
                {
                    "agent_id": str(b.agent_id),
                    "value": b.value,
                    "cost": b.cost,
                    "match": b.capability_match,
                }
                for b in bids
            ],
        }
        self._history.append(record)

        return winner, second_price, [record]

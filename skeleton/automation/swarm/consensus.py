"""Consensus protocols — majority + BFT (split from swarm_types.py, v16.2).

Fix (2026-08-28): ``AgentId.generate()`` did not exist on the kernel id
lattice (the constructor is ``AgentId.new()``), so the BFT pre-commit
crashed with AttributeError on every invocation. Uses ``AgentId.new()``.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Mapping, Optional, Tuple

from skeleton.kernel.errors import ConsensusError

from .types import AgentState

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
        ballots: Optional[Mapping[str, str]] = None,
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
        ballots: Optional[Mapping[str, str]] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        if not voters:
            raise ConsensusError("No voters available", ballot={})
        if not isinstance(ballots, Mapping) or not ballots:
            raise ConsensusError("explicit ballots are required", ballot={})
        if quorum_size is not None and (isinstance(quorum_size, bool) or not isinstance(quorum_size, int) or quorum_size < 1):
            raise ConsensusError("quorum_size must be a positive integer", ballot={})

        votes: Dict[str, float] = {"yes": 0.0, "no": 0.0, "abstain": 0.0}
        ballot_details: List[Dict[str, Any]] = []
        seen: set[str] = set()
        yes_count = 0

        for voter in voters:
            if not voter.is_alive():
                continue
            agent_id = str(voter.agent_id)
            if agent_id in seen:
                raise ConsensusError("duplicate voter", ballot={"agent_id": agent_id})
            seen.add(agent_id)
            vote = ballots.get(agent_id)
            if vote not in {"yes", "no", "abstain"}:
                raise ConsensusError("missing ballot", ballot={"agent_id": agent_id})
            weight = voter.reputation * voter.effective_capacity()
            if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not weight > 0:
                raise ConsensusError("voter weight must be positive", ballot={"agent_id": agent_id})
            votes[vote] += float(weight)
            if vote == "yes":
                yes_count += 1
            ballot_details.append({
                "agent_id": agent_id,
                "vote": vote,
                "weight": weight,
                "reputation": voter.reputation,
            })

        total_weight = sum(votes.values())
        if total_weight == 0:
            raise ConsensusError("All voters dead or quarantined", ballot={"details": ballot_details})

        threshold = total_weight / 2.0
        accepted = votes["yes"] > votes["no"] and (quorum_size is None or yes_count >= quorum_size)

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
        if isinstance(f, bool) or not isinstance(f, int) or f < 0:
            raise ConsensusError("f must be a non-negative integer", ballot={})
        self.f = f
        self.required_nodes = 3 * f + 1

    def propose(
        self,
        proposal: Any,
        voters: List[AgentState],
        *,
        quorum_size: Optional[int] = None,
        ballots: Optional[Mapping[str, str]] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        del quorum_size
        if not isinstance(ballots, Mapping) or not ballots:
            raise ConsensusError("explicit ballots are required", ballot={})
        proposal_hash = hashlib.sha256(repr(proposal).encode()).hexdigest()[:16]
        required = 2 * self.f + 1
        accepts: List[str] = []
        rejects: List[str] = []
        seen: set[str] = set()
        for voter in voters:
            if not voter.is_alive():
                continue
            agent_id = str(voter.agent_id)
            if agent_id in seen:
                raise ConsensusError("duplicate voter", ballot={"agent_id": agent_id})
            seen.add(agent_id)
            vote = ballots.get(agent_id)
            if vote not in {"accept", "reject"}:
                raise ConsensusError("missing ballot", ballot={"agent_id": agent_id})
            (accepts if vote == "accept" else rejects).append(agent_id)
        alive = len(seen)
        ballot = {
            "protocol": "explicit-bft",
            "f": self.f,
            "alive_nodes": alive,
            "accepts": accepts,
            "rejects": rejects,
            "required": required,
            "proposal_hash": proposal_hash,
            "accepted": alive >= self.required_nodes and len(accepts) >= required,
        }
        if alive < self.required_nodes:
            raise ConsensusError(
                f"Insufficient nodes for BFT: {alive} < {self.required_nodes} (f={self.f})",
                ballot=ballot,
            )
        if len(accepts) < required:
            raise ConsensusError(
                f"COMMIT phase failed: {len(accepts)} < {required}",
                ballot=ballot,
            )
        return True, ballot

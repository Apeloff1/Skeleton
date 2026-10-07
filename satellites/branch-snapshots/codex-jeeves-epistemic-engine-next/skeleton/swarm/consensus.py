"""Consensus protocols — majority + BFT (split from swarm_types.py, v16.2).

Fix (2026-08-28): ``AgentId.generate()`` did not exist on the kernel id
lattice (the constructor is ``AgentId.new()``), so the BFT pre-commit
crashed with AttributeError on every invocation. Uses ``AgentId.new()``.
"""

from __future__ import annotations

import hashlib
import random
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from skeleton.kernel.errors import ConsensusError
from skeleton.kernel.ids import AgentId

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

        proposal_hash = self._commit(proposal, AgentId.new())

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
                ballot={"phase": "pre_prepare", "accepts": len(pre_prepare_votes["accept"]),
                        "required": 2 * self.f + 1},
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
                ballot={"phase": "prepare", "accepts": len(prepare_votes["accept"]),
                        "required": 2 * self.f + 1},
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

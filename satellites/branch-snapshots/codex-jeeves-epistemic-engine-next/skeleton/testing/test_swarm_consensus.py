"""Smoke tests for the swarm consensus layer (2026-08).

Regression coverage for the two runtime crashes found during the mesh
twin audit:

  - ``ConsensusError(…, ballot=…)`` hit ``SkeletonError.__init__``, which
    never accepted a ballot kwarg → TypeError on every failed quorum.
  - ``ByzantineFaultTolerantConsensus`` called ``AgentId.generate()``,
    which does not exist (the lattice exposes ``AgentId.new()``).
"""

from __future__ import annotations

import pytest

from skeleton.kernel.errors import ConsensusError
from skeleton.kernel.ids import AgentId
from skeleton.swarm.consensus import (
    ByzantineFaultTolerantConsensus,
    SimpleMajorityConsensus,
)
from skeleton.swarm.types import AgentRole, AgentState, CapabilityVector


def _voter(*, prediction: float = 10.0, reputation: float = 1.0) -> AgentState:
    return AgentState(
        agent_id=AgentId.new(),
        role=AgentRole.WORKER,
        capabilities=CapabilityVector(compute=5.0, prediction=prediction),
        reputation=reputation,
    )


def test_consensus_error_carries_ballot_in_context():
    exc = ConsensusError("quorum failed", ballot={"yes": 1.0, "threshold": 2.0})
    assert exc.context["ballot"] == {"yes": 1.0, "threshold": 2.0}
    assert exc.ballot["yes"] == 1.0
    assert exc.to_dict()["code"] == "AGT.CONSENSUS"


def test_simple_majority_empty_voters_raises_consensus_error_not_type_error():
    with pytest.raises(ConsensusError):
        SimpleMajorityConsensus().propose("anything", [])


def test_simple_majority_all_dead_voters_raises_with_ballot():
    dead = _voter()
    dead.last_heartbeat = 0.0  # silent forever → not alive
    with pytest.raises(ConsensusError) as info:
        SimpleMajorityConsensus().propose("anything", [dead])
    assert "details" in info.value.ballot


def test_simple_majority_can_pass():
    voters = [_voter() for _ in range(5)]
    accepted, ballot = SimpleMajorityConsensus().propose("ship it", voters)
    # high-prediction voters vote yes with p=1.0
    assert accepted is True
    assert ballot["alive_voters"] == 5


def test_bft_insufficient_nodes_raises_consensus_error_not_type_error():
    with pytest.raises(ConsensusError) as info:
        ByzantineFaultTolerantConsensus(f=1).propose("x", [_voter()])
    assert info.value.ballot["required"] == 4


def test_bft_runs_without_attribute_error():
    voters = [_voter() for _ in range(4)]
    accepted, ballot = ByzantineFaultTolerantConsensus(f=1).propose("x", voters)
    assert accepted is True
    assert ballot["protocol"] == "pbft_inspired"
    assert ballot["proposal_hash"]

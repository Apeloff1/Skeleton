"""A collective decision is not invented. Voters have to say what they mean."""

import pytest

from skeleton.kernel.errors import ConsensusError
from skeleton.kernel.ids import AgentId
from skeleton.swarm.consensus import ByzantineFaultTolerantConsensus, SimpleMajorityConsensus
from skeleton.swarm.hive import AggregationError, Estimate, HiveMind
from skeleton.swarm.quorum import QuorumError, QuorumSensor
from skeleton.swarm.types import AgentRole, AgentState, AgentStatus, CapabilityVector


def _voter(name: str) -> AgentState:
    return AgentState(
        agent_id=AgentId(name),
        role=AgentRole.WORKER,
        capabilities=CapabilityVector(compute=1.0),
    )


def test_majority_and_bft_use_the_ballots_they_were_given() -> None:
    voters = [_voter("a"), _voter("b"), _voter("c"), _voter("d")]
    majority = SimpleMajorityConsensus()
    with pytest.raises(ConsensusError):
        majority.propose("ship", voters)
    accepted, ballot = majority.propose(
        "ship",
        voters,
        ballots={"a": "yes", "b": "yes", "c": "yes", "d": "no"},
    )
    assert accepted is True
    assert ballot["votes"]["yes"] > ballot["votes"]["no"]
    with pytest.raises(ConsensusError):
        majority.propose("ship", voters, ballots={"a": "no", "b": "no", "c": "yes", "d": "abstain"})

    bft = ByzantineFaultTolerantConsensus(f=1)
    with pytest.raises(ConsensusError):
        bft.propose("ship", voters, ballots={"a": "accept", "b": "reject", "c": "reject", "d": "reject"})
    ok, record = bft.propose(
        "ship",
        voters,
        ballots={"a": "accept", "b": "accept", "c": "accept", "d": "reject"},
    )
    assert ok is True
    assert record["accepts"] == ["a", "b", "c"]
    assert record["proposal_hash"] == bft.propose(
        "ship",
        voters,
        ballots={"a": "accept", "b": "accept", "c": "accept", "d": "accept"},
    )[1]["proposal_hash"]


def test_a_split_crowd_is_not_an_estimate_and_a_negative_signal_is_not_support() -> None:
    hive = HiveMind()
    agreed = hive.aggregate([Estimate("a", 10), Estimate("b", 10), Estimate("c", 10)], method="mean")
    assert agreed.value == 10
    assert agreed.trustworthy is True
    with pytest.raises(AggregationError):
        hive.aggregate([Estimate("a", 0), Estimate("b", 100)], method="mean")
    with pytest.raises(AggregationError):
        hive.aggregate([Estimate("a", 10, weight=-1)])

    sensor = QuorumSensor(population_probe=lambda: 4)
    sensor.register_behaviour("hunt")
    with pytest.raises(QuorumError):
        sensor.emit("a", "hunt", weight=-5)
    sensor.emit("a", "hunt")
    assert sensor.evaluate("hunt").state.value == "dormant"

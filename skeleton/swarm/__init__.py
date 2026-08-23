"""Swarm package — intelligence mesh (split from swarm_types.py + swarm_mesh.py, v16.2)."""

from .types import AgentRole, CapabilityVector, AgentStatus, AgentState
from .consensus import ConsensusProtocol, SimpleMajorityConsensus, ByzantineFaultTolerantConsensus
from .auction import AuctionBid, VickreyAuction
from .mesh import SwarmMesh

__all__ = [
    "AgentRole",
    "CapabilityVector",
    "AgentStatus",
    "AgentState",
    "ConsensusProtocol",
    "SimpleMajorityConsensus",
    "ByzantineFaultTolerantConsensus",
    "AuctionBid",
    "VickreyAuction",
    "SwarmMesh",
]

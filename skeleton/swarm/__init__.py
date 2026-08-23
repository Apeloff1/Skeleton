"""Swarm package — intelligence mesh (split from swarm_types.py + swarm_mesh.py, v16.2)."""

from .types import AgentRole, CapabilityVector, AgentStatus, AgentState
from .consensus import ConsensusProtocol, SimpleMajorityConsensus, ByzantineFaultTolerantConsensus
from .auction import AuctionBid, VickreyAuction
from .mesh import SwarmMesh
from .stigmergy import Trail, PheromoneField, StigmergicRouter

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
    "Trail",
    "PheromoneField",
    "StigmergicRouter",
]

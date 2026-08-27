"""Swarm package — intelligence mesh (split from swarm_types + swarm_mesh, v16.2)."""

from .types import AgentRole, CapabilityVector, AgentStatus, AgentState
from .consensus import ConsensusProtocol, SimpleMajorityConsensus, ByzantineFaultTolerantConsensus
from .auction import AuctionBid, VickreyAuction
from .mesh import SwarmMesh
from .stigmergy import Trail, PheromoneField, StigmergicRouter
from .roles import RoleRegistry, RoleError, default_roles

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
    "RoleRegistry",
    "RoleError",
    "default_roles",
]

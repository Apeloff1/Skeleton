"""Swarm package — intelligence mesh (split from swarm_types + swarm_mesh, v16.2)."""

from .types import AgentRole, CapabilityVector, AgentStatus, AgentState
from .consensus import ConsensusProtocol, SimpleMajorityConsensus, ByzantineFaultTolerantConsensus
from .auction import AuctionBid, VickreyAuction
from .mesh import SwarmMesh
from .stigmergy import Trail, PheromoneField, StigmergicRouter
from .roles import RoleRegistry, RoleError, default_roles
from .hive import HiveMind, HiveResult, AggregationError
from .blackboard import Blackboard, BlackboardEntry
from .handoff import HandoffError, HandoffRegistry, TaskEnvelope, TaskState
from .mesh_boundary import mesh_boundary
from .mesh_handoff import MeshHandoffAdapter

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
    "HiveMind",
    "HiveResult",
    "AggregationError",
    "Blackboard",
    "BlackboardEntry",
    "HandoffError",
    "HandoffRegistry",
    "TaskEnvelope",
    "TaskState",
    "mesh_boundary",
    "MeshHandoffAdapter",
]

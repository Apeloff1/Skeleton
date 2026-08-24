"""Swarm package — intelligence mesh (split from swarm_types.py + swarm_mesh.py, v16.2)."""

from .types import AgentRole, CapabilityVector, AgentStatus, AgentState
from .consensus import ConsensusProtocol, SimpleMajorityConsensus, ByzantineFaultTolerantConsensus
from .auction import AuctionBid, VickreyAuction
from .mesh import SwarmMesh
from .hive import AggregationError, Estimate, HiveMind, HiveResult
from .negotiation import CapabilityNegotiator, Contract, NegotiationError, NegotiationFailure, Offer
from .platoons import Doctrine, OraclePlatoon, Platoon, PlatoonReport, standard_platoons
from .stigmergy import PheromoneField, StigmergicRouter, Trail

__all__ = [
    "AgentRole", "CapabilityVector", "AgentStatus", "AgentState",
    "ConsensusProtocol", "SimpleMajorityConsensus", "ByzantineFaultTolerantConsensus",
    "AuctionBid", "VickreyAuction", "SwarmMesh",
    "HiveMind", "Estimate", "HiveResult", "AggregationError",
    "CapabilityNegotiator", "Contract", "Offer", "NegotiationFailure", "NegotiationError",
    "Platoon", "OraclePlatoon", "PlatoonReport", "Doctrine", "standard_platoons",
    "PheromoneField", "StigmergicRouter", "Trail",
]

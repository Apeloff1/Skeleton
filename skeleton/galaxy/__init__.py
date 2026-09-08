"""Skeleton Galaxy Package — transport, consensus, KAG sync, routing, election."""

from skeleton.galaxy.federation import (
    FederationMesh,
    GalaxyNode,
    NodeIdentity,
    NodeRegistry,
)
from skeleton.galaxy.transport import NodeTransport
from skeleton.galaxy.consensus import ConsensusEngine, Proposal
from skeleton.galaxy.kag_sync import KAGSync
from skeleton.galaxy.galaxy_bridge import GalaxyBridge, RemoteTask
from skeleton.galaxy.election import LeaderElection, LeadershipState

__all__ = [
    "GalaxyNode",
    "FederationMesh",
    "NodeRegistry",
    "NodeIdentity",
    "NodeTransport",
    "ConsensusEngine",
    "Proposal",
    "KAGSync",
    "GalaxyBridge",
    "RemoteTask",
    "LeaderElection",
    "LeadershipState",
]

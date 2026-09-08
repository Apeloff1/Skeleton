"""Skeleton Galaxy Package — with transport, consensus, and KAG sync."""

from skeleton.galaxy.federation import (
    FederationMesh,
    GalaxyNode,
    NodeIdentity,
    NodeRegistry,
)
from skeleton.galaxy.transport import NodeTransport
from skeleton.galaxy.consensus import ConsensusEngine, Proposal
from skeleton.galaxy.kag_sync import KAGSync

__all__ = [
    "GalaxyNode",
    "FederationMesh",
    "NodeRegistry",
    "NodeIdentity",
    "NodeTransport",
    "ConsensusEngine",
    "Proposal",
    "KAGSync",
]

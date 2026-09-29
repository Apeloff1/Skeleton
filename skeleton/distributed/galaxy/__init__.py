"""Skeleton Galaxy Package — full federation stack."""

from skeleton.distributed.galaxy.federation import (
    FederationMesh,
    GalaxyNode,
    NodeIdentity,
    NodeRegistry,
)
from skeleton.distributed.galaxy.transport import NodeTransport
from skeleton.distributed.galaxy.consensus import ConsensusEngine, Proposal
from skeleton.distributed.galaxy.kag_sync import KAGSync
from skeleton.distributed.galaxy.galaxy_bridge import GalaxyBridge, RemoteTask
from skeleton.distributed.galaxy.election import LeaderElection, LeadershipState
from skeleton.distributed.galaxy.fleet import FleetCoordinator, LoadLedger

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
    "FleetCoordinator",
    "LoadLedger",
]

"""
Skeleton Galaxy Package

Exports:
- GalaxyNode: Distributed node
- FederationMesh: Cross-node communication
- NodeRegistry: Node discovery
- NodeIdentity: Node metadata
"""

from skeleton.galaxy.federation import (
    FederationMesh,
    GalaxyNode,
    NodeIdentity,
    NodeRegistry,
)

__all__ = [
    "GalaxyNode",
    "FederationMesh",
    "NodeRegistry",
    "NodeIdentity",
]

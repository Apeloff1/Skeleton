"""
Skeleton Swarm Package

Exports:
- SwarmMesh: Agent routing mesh
- PheromoneField: Stigmergic communication
- HiveMind: Collective reasoning
- CapabilityNegotiator: Dynamic capability discovery
- Platoons: Pre-configured agent groups
- StigmergicRouter: Pheromone-influenced routing
"""

from skeleton.swarm.mesh import (
    Agent,
    CapabilityNegotiator,
    HiveMind,
    PheromoneField,
    Platoons,
    StigmergicRouter,
    SwarmMesh,
    standard_platoons,
)

__all__ = [
    "SwarmMesh",
    "Agent",
    "PheromoneField",
    "StigmergicRouter",
    "HiveMind",
    "CapabilityNegotiator",
    "Platoons",
    "standard_platoons",
]

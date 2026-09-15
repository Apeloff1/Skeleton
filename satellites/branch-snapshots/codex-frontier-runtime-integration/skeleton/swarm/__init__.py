"""
Skeleton Swarm Package

Exports:
- SwarmMesh: Agent routing mesh
- PheromoneField: Stigmergic communication
- HiveMind: Collective reasoning
- CapabilityNegotiator: Dynamic capability discovery
- Platoons: Pre-configured agent groups
- StigmergicRouter: Pheromone-influenced routing
- SwarmDag / TaskNode / TaskStatus / SubmitError: attested task DAG
- ReadyWaveRunner: sync drain of ready_wave → claim → attested complete
"""

from skeleton.swarm.dag import SubmitError, SwarmDag, TaskNode, TaskStatus
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
from skeleton.swarm.ready_wave_runner import ReadyWaveReport, ReadyWaveRunner

__all__ = [
    "SwarmMesh",
    "Agent",
    "PheromoneField",
    "StigmergicRouter",
    "HiveMind",
    "CapabilityNegotiator",
    "Platoons",
    "standard_platoons",
    "SwarmDag",
    "TaskNode",
    "TaskStatus",
    "SubmitError",
    "ReadyWaveRunner",
    "ReadyWaveReport",
]

"""Swarm public facade.

GB-29's `Mesh`/handoff contracts are canonical. Legacy routing exports remain
available for Genesis and compatibility callers while those surfaces migrate.
"""

from __future__ import annotations

from skeleton.swarm.capabilities import capabilities
from skeleton.swarm.dag import SubmitError, SwarmDag, TaskNode, TaskStatus
from skeleton.swarm.law import N_CAP, PACKET, VERSION
from skeleton.swarm.mesh import (
    Agent,
    CapabilityNegotiator,
    HiveMind,
    Mesh,
    PheromoneField,
    Platoons,
    StigmergicRouter,
    SwarmMesh,
    standard_platoons,
)
from skeleton.swarm.mesh_boundary import boundary
from skeleton.swarm.mesh_handoff import handoff
from skeleton.swarm.ready_wave_runner import ReadyWaveReport, ReadyWaveRunner

__all__ = [
    "N_CAP",
    "PACKET",
    "VERSION",
    "Mesh",
    "boundary",
    "capabilities",
    "handoff",
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

"""Swarm mesh facade (GB-29). No second diet."""

from __future__ import annotations

from skeleton.swarm.capabilities import capabilities
from skeleton.swarm.law import N_CAP, PACKET, VERSION
from skeleton.swarm.mesh import Mesh
from skeleton.swarm.mesh_boundary import boundary
from skeleton.swarm.mesh_handoff import handoff

__all__ = [
    "N_CAP",
    "PACKET",
    "VERSION",
    "Mesh",
    "boundary",
    "capabilities",
    "handoff",
]

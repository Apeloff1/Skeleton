"""Service mesh-lite for gate-plane s2s clients: peer health + sticky routing.

Pure library code with injectable clocks and RNG; no background threads and
no changes to ``skeleton/api/server.py``.
"""

from __future__ import annotations

from skeleton.gate_plane.mesh.peers import Endpoint, HealthConfig, PeerHealth, PeerSet, PeerState, Probe
from skeleton.gate_plane.mesh.routing import MeshClient, NoEndpointAvailable, STICKY_HEADER, Selector, rendezvous_rank

__all__ = [
    "Endpoint",
    "HealthConfig",
    "MeshClient",
    "NoEndpointAvailable",
    "PeerHealth",
    "PeerSet",
    "PeerState",
    "Probe",
    "STICKY_HEADER",
    "Selector",
    "rendezvous_rank",
]

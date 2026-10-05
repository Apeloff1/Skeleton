"""Twin-mesh note — boundary between agents/mesh.py and swarm/mesh.py.

Two meshes coexist deliberately after the 2026-08-28 audit:

- :class:`skeleton.agents.mesh.AgentMesh` — the operational roster: join/
  leave/heartbeat, least-loaded routing by capability string, TTL-based
  quarantine/eviction, weighted simple-majority consensus. This is the mesh
  the API layer (``skeleton/api/server.py`` AppState) wires.

- :class:`skeleton.swarm.mesh.SwarmMesh` — the research substrate: partition
  detection/healing, circuit breakers, chaos injection, Vickrey auction
  allocation, reputation-weighted routing over :class:`CapabilityVector`.
  Genesis wires this one as the ``swarm.mesh`` handle.

They serve different layers and both are live — do NOT fold one into the
other. The contract that keeps them honest:

  1. Agent identity is shared: both key agents by ``kernel.ids.AgentId``.
  2. Errors are shared: both raise from ``kernel.errors`` (ConsensusError
     carries ballots as of the 2026-08-28 fix).
  3. If a unified roster is ever wanted, SwarmMesh gains an AgentMesh
     adapter — not the reverse (AgentMesh is the simpler contract and the
     API depends on its exact surface).
"""

from __future__ import annotations


def mesh_boundary() -> dict:
    """Introspectable record of the deliberate two-mesh boundary."""
    return {
        "operational": {
            "class": "skeleton.agents.mesh.AgentMesh",
            "wired_by": "skeleton/api/server.py (AppState.mesh)",
            "concerns": ["roster", "capability routing", "ttl liveness", "majority consensus"],
        },
        "research": {
            "class": "skeleton.swarm.mesh.SwarmMesh",
            "wired_by": "skeleton/genesis.py (_phase_swarm)",
            "concerns": ["partitions", "circuit breakers", "chaos", "auctions", "reputation routing"],
        },
        "shared": ["kernel.ids.AgentId", "kernel.errors.ConsensusError", "kernel.events.EventBus"],
        "rule": "Do not fold; if unifying, adapt SwarmMesh onto AgentMesh's roster contract.",
    }

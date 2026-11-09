"""
Skeleton — Round-11 architecture addendum

Cross-node task routing round: GalaxyBridge routes Coordinator tasks
to remote galaxy nodes when no local agent serves the capability.
"""

from __future__ import annotations

from typing import Any, Dict


NEW_MODULES: Dict[str, Dict[str, Any]] = {
    "skeleton.galaxy.galaxy_bridge": {
        "layer": "galaxy",
        "purpose": "GalaxyBridge: local-first task dispatch with remote offer/accept/result over transport",
        "exports": ["GalaxyBridge", "RemoteTask"],
    },
}

ROUTING_FLOW = [
    "Task dispatched: try local swarm mesh first",
    "No local agent: offer to remote nodes advertising the capability",
    "Remote node with a registered handler accepts",
    "Remote executes, result returns over the wire",
    "Stale offers expire after TTL",
]


def summary() -> Dict[str, Any]:
    return {
        "round11_modules": len(NEW_MODULES),
        "routing_flow_stages": len(ROUTING_FLOW),
        "routing_flow": ROUTING_FLOW,
        "genesis_handles_galaxy": ["galaxy", "galaxy_transport", "consensus", "kag_sync", "galaxy_bridge"],
    }

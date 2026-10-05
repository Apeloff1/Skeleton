"""
Skeleton — Round-9 architecture addendum

Consensus round: proposals and votes travel the live galaxy transport;
genesis galaxy phase wires a ConsensusEngine handle.
"""

from __future__ import annotations

from typing import Any, Dict


NEW_MODULES: Dict[str, Dict[str, Any]] = {
    "skeleton.galaxy.consensus": {
        "layer": "galaxy",
        "purpose": "ConsensusEngine: Raft-lite propose/vote/outcome over NodeTransport with local policy voters",
        "exports": ["ConsensusEngine", "Proposal"],
    },
}

CONSENSUS_FLOW = [
    "Node A proposes (topic, value)",
    "Broadcast via transport to all known peers",
    "Peers apply local policy voters and vote back",
    "Proposer tallies simple majority of electorate",
    "Outcome broadcast marks every node's local copy",
]


def summary() -> Dict[str, Any]:
    return {
        "round9_modules": len(NEW_MODULES),
        "consensus_flow_stages": len(CONSENSUS_FLOW),
        "consensus_flow": CONSENSUS_FLOW,
        "genesis_handles_galaxy": ["galaxy", "galaxy_transport", "consensus"],
    }

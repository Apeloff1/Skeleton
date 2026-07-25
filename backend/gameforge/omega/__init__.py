"""
gameforge.omega — Ω-ULTRA CONDUCTOR (production merge for AI systems).

A battle-ready, async, distributed, spacetime-aware fail-safe context/progress
engine for real AI agents. Guarantees: never-repeat pages (Bloom+HLL), causal
ordering (DAG), Byzantine quorum (PBFT-sim), content purge@5, immortal
pagecount (TMR), fresh-on-begin, async queues, Kalman ETA, Merkle proofs.

Powers the upgraded context system, Jeeves, the Jeeves orchestrator, agents,
agent↔agent hand-offs, the agent map and the mastermap via a single engine +
role-specialised wrappers + an in-process session registry.
"""
from gameforge.omega.conductor import (
    OmegaUltraConductor,
    AgentToAgentConductor,
    OrchestratorConductor,
    UserToJeevesConductor,
    ConductorRegistry,
    conductor_registry,
    IntegrityError, RecoverableError, RepetitionError,
    ConsensusError, MarathonStateError, QueueOverflowError,
)
from gameforge.omega.integration import OmegaFabric, omega_fabric

__all__ = [
    "OmegaUltraConductor", "AgentToAgentConductor", "OrchestratorConductor",
    "UserToJeevesConductor", "ConductorRegistry", "conductor_registry",
    "OmegaFabric", "omega_fabric",
    "IntegrityError", "RecoverableError", "RepetitionError",
    "ConsensusError", "MarathonStateError", "QueueOverflowError",
]

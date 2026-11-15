"""
gameforge.omega — Ω-ULTRA CONDUCTOR (production merge for AI systems).

A bounded session-local context/progress engine: exact deduplication, causal
ordering, in-process quorum simulation, content retention, monotonic progress,
async queues and Merkle content inclusion proofs. No distributed or durable
session qualification is implied.

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
from gameforge.omega.delta_memory import DeltaMemory, delta_memory
from gameforge.omega.legions import LegionCommand, legion_command, Legion

__all__ = [
    "OmegaUltraConductor", "AgentToAgentConductor", "OrchestratorConductor",
    "UserToJeevesConductor", "ConductorRegistry", "conductor_registry",
    "OmegaFabric", "omega_fabric",
    "DeltaMemory", "delta_memory",
    "LegionCommand", "legion_command", "Legion",
    "IntegrityError", "RecoverableError", "RepetitionError",
    "ConsensusError", "MarathonStateError", "QueueOverflowError",
]

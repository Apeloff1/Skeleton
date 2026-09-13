"""Frontier consolidation contracts and program metadata."""

from skeleton.frontier.contracts import AgentContract, MemoryContract, ProvenanceRecord
from skeleton.frontier.npc import NPCGenerator, NPCSpec

__all__ = [
    "AgentContract",
    "MemoryContract",
    "NPCGenerator",
    "NPCSpec",
    "ProvenanceRecord",
]

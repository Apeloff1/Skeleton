"""Frontier consolidation contracts and program metadata."""

from skeleton.frontier.agent_runtime import AgentRuntime, ExecutionResult
from skeleton.frontier.contracts import AgentContract, MemoryContract, ProvenanceRecord
from skeleton.frontier.memory import InMemoryStore, MemoryItem
from skeleton.frontier.npc import NPCGenerator, NPCSpec

__all__ = [
    "AgentContract",
    "AgentRuntime",
    "ExecutionResult",
    "InMemoryStore",
    "MemoryContract",
    "MemoryItem",
    "NPCGenerator",
    "NPCSpec",
    "ProvenanceRecord",
]

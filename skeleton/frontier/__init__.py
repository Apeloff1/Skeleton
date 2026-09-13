"""Frontier consolidation contracts and program metadata."""

from skeleton.frontier.agent_runtime import AgentRuntime, ExecutionResult
from skeleton.frontier.contracts import AgentContract, MemoryContract, ProvenanceRecord
from skeleton.frontier.memory import InMemoryStore, MemoryItem
from skeleton.frontier.npc import NPCGenerator, NPCSpec
from skeleton.frontier.npc_profiles import ArchetypeProfile, get_profile, infer_archetype
from skeleton.frontier.resilience import DegradationLevel, ResilienceController, ResilienceDecision

__all__ = [
    "AgentContract",
    "AgentRuntime",
    "ArchetypeProfile",
    "DegradationLevel",
    "ExecutionResult",
    "InMemoryStore",
    "MemoryContract",
    "MemoryItem",
    "NPCGenerator",
    "NPCSpec",
    "ProvenanceRecord",
    "ResilienceController",
    "ResilienceDecision",
    "get_profile",
    "infer_archetype",
]

"""Frontier consolidation contracts and program metadata."""

from skeleton.frontier.agent_runtime import AgentRuntime, ExecutionResult
from skeleton.frontier.contracts import (
    AgentContract,
    MemoryContract,
    ProvenanceRecord,
    stable_content_digest,
)
from skeleton.frontier.events import DomainEvent, EventBus
from skeleton.frontier.memory import InMemoryStore, MemoryItem
from skeleton.frontier.memory_adapters import CollectionMemoryAdapter, SQLiteCollection
from skeleton.frontier.npc import NPCGenerator, NPCSpec
from skeleton.frontier.npc_adapters import npc_spec_from_domain_record
from skeleton.frontier.npc_profiles import ArchetypeProfile, get_profile, infer_archetype
from skeleton.frontier.resilience import DegradationLevel, ResilienceController, ResilienceDecision

__all__ = [
    "AgentContract",
    "AgentRuntime",
    "ArchetypeProfile",
    "CollectionMemoryAdapter",
    "DegradationLevel",
    "DomainEvent",
    "EventBus",
    "ExecutionResult",
    "InMemoryStore",
    "MemoryContract",
    "MemoryItem",
    "NPCGenerator",
    "NPCSpec",
    "ProvenanceRecord",
    "ResilienceController",
    "ResilienceDecision",
    "SQLiteCollection",
    "get_profile",
    "infer_archetype",
    "npc_spec_from_domain_record",
    "stable_content_digest",
]

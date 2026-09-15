"""Frontier consolidation contracts and program metadata."""

from skeleton.frontier.agent_runtime import AgentRuntime, ExecutionResult
from skeleton.frontier.contracts import (
    AgentContract,
    MemoryContract,
    ProvenanceRecord,
    stable_content_digest,
)
from skeleton.frontier.events import (
    DomainEvent,
    EventBus,
    EventJournal,
    JournalEntry,
    SQLiteEventJournal,
)
from skeleton.frontier.memory import InMemoryStore, MemoryItem
from skeleton.frontier.memory_adapters import CollectionMemoryAdapter, SQLiteCollection
from skeleton.frontier.npc import NPCGenerator, NPCSpec
from skeleton.frontier.npc_adapters import npc_spec_from_domain_record
from skeleton.frontier.npc_profiles import ArchetypeProfile, get_profile, infer_archetype
from skeleton.frontier.resilience import DegradationLevel, ResilienceController, ResilienceDecision
from skeleton.frontier.world import (
    IslandVocabulary,
    WorldBounds,
    WorldRegion,
    calculate_route,
    calculate_supplies_needed,
    find_region_at,
    find_region_by_id,
    generate_random_island,
    project_fog_of_war,
    region_from_record,
)

__all__ = [
    "AgentContract",
    "AgentRuntime",
    "ArchetypeProfile",
    "CollectionMemoryAdapter",
    "DegradationLevel",
    "DomainEvent",
    "EventBus",
    "EventJournal",
    "ExecutionResult",
    "InMemoryStore",
    "IslandVocabulary",
    "JournalEntry",
    "MemoryContract",
    "MemoryItem",
    "NPCGenerator",
    "NPCSpec",
    "ProvenanceRecord",
    "ResilienceController",
    "ResilienceDecision",
    "SQLiteCollection",
    "SQLiteEventJournal",
    "WorldBounds",
    "WorldRegion",
    "calculate_route",
    "calculate_supplies_needed",
    "find_region_at",
    "find_region_by_id",
    "generate_random_island",
    "get_profile",
    "infer_archetype",
    "npc_spec_from_domain_record",
    "project_fog_of_war",
    "region_from_record",
    "stable_content_digest",
]

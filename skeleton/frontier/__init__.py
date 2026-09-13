"""Frontier consolidation contracts and program metadata."""

from skeleton.frontier.agent_runtime import AgentRuntime, ExecutionResult
from skeleton.frontier.capabilities import CapabilityPolicy
from skeleton.frontier.contracts import AgentContract, MemoryContract, ProvenanceRecord
from skeleton.frontier.events import DomainEvent, EventBus
from skeleton.frontier.execution import ExecutionPolicy, ExecutionStatus, RuntimeBusy, RuntimeClosed, TransientAgentError
from skeleton.frontier.health import HealthReport, HealthState, evaluate_health
from skeleton.frontier.learning import LearningState, Mastery, assess
from skeleton.frontier.lore import LoreEntry, LoreIndex
from skeleton.frontier.memory import InMemoryStore, MemoryItem
from skeleton.frontier.npc import NPCGenerator, NPCSpec
from skeleton.frontier.npc_profiles import ArchetypeProfile, get_profile, infer_archetype
from skeleton.frontier.resilience import DegradationLevel, ResilienceController, ResilienceDecision
from skeleton.frontier.simulation import GenerationRequest, SimulationTick, stable_seed
from skeleton.frontier.singleflight import IdempotencyConflict, SingleFlight
from skeleton.frontier.sqlite_memory import SQLiteMemoryStore
from skeleton.frontier.telemetry import MetricSample, TelemetryBuffer

__all__ = [
    "AgentContract", "AgentRuntime", "ArchetypeProfile", "CapabilityPolicy",
    "DegradationLevel", "DomainEvent", "EventBus", "ExecutionResult",
    "GenerationRequest", "HealthReport", "HealthState", "InMemoryStore",
    "LearningState", "LoreEntry", "LoreIndex", "Mastery", "MemoryContract",
    "MemoryItem", "MetricSample", "NPCGenerator", "NPCSpec", "ProvenanceRecord",
    "ResilienceController", "ResilienceDecision", "SimulationTick",
    "TelemetryBuffer", "assess", "evaluate_health", "get_profile", "infer_archetype",
    "stable_seed",
    "ExecutionPolicy", "ExecutionStatus", "RuntimeBusy", "RuntimeClosed", "TransientAgentError",
    "IdempotencyConflict", "SingleFlight", "SQLiteMemoryStore",
]

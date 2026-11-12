"""Pure domain kernel. Zero I/O. Completionist Nov 2026."""
from .errors import SkeletonError, DomainError, Severity
from .events import DomainEvent, EventBus
from .ids import GameId, RunId, AgentId, SessionId
from .registry import CapabilityRegistry
__all__ = ["SkeletonError", "DomainError", "Severity", "DomainEvent", "EventBus", "GameId", "RunId", "AgentId", "SessionId", "CapabilityRegistry"]

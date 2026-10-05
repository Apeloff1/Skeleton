"""Swarm types — roles, capabilities, agent state (split from swarm_types.py, v16.2)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Optional, Set

from skeleton.kernel.ids import AgentId

# =============================================================================
# AGENT ROLES AND CAPABILITY VECTORS
# =============================================================================

class AgentRole(Enum):
    SCOUT = auto()      # Discovery, reconnaissance, information gathering
    WORKER = auto()     # Execution, computation, task completion
    GUARDIAN = auto()   # Security, validation, fault detection
    ORACLE = auto()     # Prediction, estimation, advisory


@dataclass
class CapabilityVector:
    """Multi-dimensional capability scoring for agent specialisation."""
    compute: float = 0.0        # Raw computation power
    memory: float = 0.0         # Memory capacity / recall precision
    network: float = 0.0       # Communication bandwidth / latency
    security: float = 0.0      # Validation / cryptographic strength
    prediction: float = 0.0    # Forecasting / estimation accuracy
    creativity: float = 0.0    # Generative / novel solution capacity

    def dot(self, other: "CapabilityVector") -> float:
        return (
            self.compute * other.compute +
            self.memory * other.memory +
            self.network * other.network +
            self.security * other.security +
            self.prediction * other.prediction +
            self.creativity * other.creativity
        )

    def magnitude(self) -> float:
        return (self.compute**2 + self.memory**2 + self.network**2 +
                self.security**2 + self.prediction**2 + self.creativity**2) ** 0.5

    def similarity(self, other: "CapabilityVector") -> float:
        mag = self.magnitude() * other.magnitude()
        return self.dot(other) / mag if mag > 0 else 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "compute": self.compute,
            "memory": self.memory,
            "network": self.network,
            "security": self.security,
            "prediction": self.prediction,
            "creativity": self.creativity,
        }


# =============================================================================
# AGENT STATE
# =============================================================================

class AgentStatus(Enum):
    HEALTHY = auto()
    BUSY = auto()
    QUARANTINED = auto()
    FAILED = auto()
    RECOVERING = auto()


@dataclass
class AgentState:
    """Complete state of a swarm agent."""
    agent_id: AgentId
    role: AgentRole
    capabilities: CapabilityVector
    status: AgentStatus = AgentStatus.HEALTHY
    health_score: float = 1.0          # 0.0 - 1.0
    reputation: float = 1.0            # Cumulative trust score
    load_factor: float = 0.0         # 0.0 - 1.0 (current utilisation)
    last_heartbeat: float = field(default_factory=time.time)
    heartbeat_interval: float = 5.0   # seconds
    consecutive_failures: int = 0
    max_failures: int = 3
    tasks_completed: int = 0
    tasks_failed: int = 0
    latency_ms: float = 0.0
    peers: Set[AgentId] = field(default_factory=set)
    assigned_capabilities: Set[str] = field(default_factory=set)

    def is_alive(self, now: Optional[float] = None) -> bool:
        now = now or time.time()
        return (
            self.status not in (AgentStatus.FAILED, AgentStatus.QUARANTINED)
            and (now - self.last_heartbeat) < self.heartbeat_interval * 3
        )

    def update_reputation(self, success: bool, weight: float = 1.0) -> None:
        """Update reputation using exponential moving average."""
        alpha = 0.1 * weight
        if success:
            self.reputation = (1 - alpha) * self.reputation + alpha * 1.0
            self.tasks_completed += 1
        else:
            self.reputation = (1 - alpha) * self.reputation + alpha * 0.0
            self.tasks_failed += 1
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.max_failures:
                self.status = AgentStatus.QUARANTINED
        if success:
            self.consecutive_failures = 0

    def effective_capacity(self) -> float:
        """Effective capacity = capability magnitude * health * (1 - load)."""
        return self.capabilities.magnitude() * self.health_score * (1.0 - self.load_factor)

"""Load-shedding decisions for overload protection at the swarm edge."""
from __future__ import annotations
from dataclasses import dataclass
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask
from skeleton.intelligence.shared_pressure import SqliteSharedPressureLedger

@dataclass(frozen=True, slots=True)
class ShedDecision:
    admit: bool
    reason: str
    queue_pressure: float

@dataclass(frozen=True, slots=True)
class LoadShedPolicy:
    max_queue_pressure: float = 100.0
    protect_priority_at_or_below: int = 10
    def __post_init__(self) -> None:
        if self.max_queue_pressure <= 0: raise ValueError("max_queue_pressure must be positive")
    def evaluate(self, runtime: SwarmRuntime, task: SwarmTask) -> ShedDecision:
        snap = runtime.snapshot(); pressure = snap.queued / max(1, snap.available_slots)
        if task.priority <= self.protect_priority_at_or_below:
            return ShedDecision(True, "protected priority", pressure)
        if pressure >= self.max_queue_pressure:
            return ShedDecision(False, "queue pressure limit exceeded", pressure)
        return ShedDecision(True, "within pressure budget", pressure)


@dataclass(frozen=True, slots=True)
class SharedLoadShedPolicy:
    """Agent-edge adapter for the durable shared pressure authority."""

    ledger: SqliteSharedPressureLedger
    scope: str

    def evaluate(
        self,
        tenant_id: str,
        *,
        priority: int = 100,
        for_queue: bool = False,
        now: float | None = None,
    ) -> ShedDecision:
        decision = self.ledger.decide(
            self.scope,
            tenant_id,
            priority=priority,
            for_queue=for_queue,
            now=now,
        )
        return ShedDecision(
            decision.admitted,
            decision.reason,
            decision.snapshot.pressure_ratio,
        )

"""High-level resilience supervisor combining quarantine, circuits and load shedding."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from math import isfinite
from time import monotonic
from typing import Callable, Mapping
from skeleton.automation.agents.swarm_load_shed import LoadShedPolicy, ShedDecision
from skeleton.automation.agents.swarm_circuit import CircuitBreaker
from skeleton.automation.agents.swarm_quarantine import QuarantineController
from skeleton.automation.agents.swarm_resilient_scheduler import ResilientSwarmScheduler
from skeleton.automation.agents.swarm_runtime import SwarmRuntime, SwarmTask, WorkerState

@dataclass(frozen=True, slots=True)
class DispatchDecision:
    accepted: bool
    worker_id: str | None
    reason: str

class SwarmSupervisor:
    STATE_VERSION = 1

    def __init__(
        self,
        *,
        shed_policy: LoadShedPolicy | None = None,
        breaker: CircuitBreaker | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.shed_policy = shed_policy or LoadShedPolicy()
        self.quarantine = QuarantineController(clock=clock)
        self.scheduler = ResilientSwarmScheduler(
            breaker or CircuitBreaker(clock=clock)
        )
        self._clock = clock

    def export_state(self) -> dict[str, object]:
        return {
            "version": self.STATE_VERSION,
            "shed_policy": {
                "max_queue_pressure": self.shed_policy.max_queue_pressure,
                "protect_priority_at_or_below": self.shed_policy.protect_priority_at_or_below,
            },
            "quarantine": self.quarantine.export_state(),
            "circuit_breaker": self.scheduler.breaker.export_state(),
        }

    @classmethod
    def from_state(
        cls,
        state: Mapping[str, object],
        *,
        clock: Callable[[], float] = monotonic,
    ) -> "SwarmSupervisor":
        required = {
            "version", "shed_policy", "quarantine", "circuit_breaker"
        }
        if not isinstance(state, Mapping) or set(state) != required:
            raise ValueError("invalid swarm supervisor state envelope")
        if state.get("version") != cls.STATE_VERSION:
            raise ValueError("unsupported swarm supervisor state version")
        raw_shed = state.get("shed_policy")
        if not isinstance(raw_shed, Mapping) or set(raw_shed) != {
            "max_queue_pressure", "protect_priority_at_or_below"
        }:
            raise ValueError("invalid load-shed policy state")
        pressure = raw_shed.get("max_queue_pressure")
        priority = raw_shed.get("protect_priority_at_or_below")
        if (
            isinstance(pressure, bool)
            or not isinstance(pressure, (int, float))
            or not isfinite(float(pressure))
            or float(pressure) <= 0
        ):
            raise ValueError("invalid restored max_queue_pressure")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ValueError("invalid restored protected priority")
        quarantine_state = state.get("quarantine")
        circuit_state = state.get("circuit_breaker")
        if not isinstance(quarantine_state, Mapping):
            raise ValueError("invalid restored quarantine state")
        if not isinstance(circuit_state, Mapping):
            raise ValueError("invalid restored circuit state")
        supervisor = cls(
            shed_policy=LoadShedPolicy(
                max_queue_pressure=float(pressure),
                protect_priority_at_or_below=priority,
            ),
            breaker=CircuitBreaker.from_state(circuit_state, clock=clock),
            clock=clock,
        )
        supervisor.quarantine = QuarantineController.from_state(
            quarantine_state,
            clock=clock,
        )
        return supervisor
    def dispatch(self, runtime: SwarmRuntime, task: SwarmTask) -> DispatchDecision:
        shed = self.shed_policy.evaluate(runtime, task)
        if not shed.admit: return DispatchDecision(False, None, shed.reason)
        ranking = self.scheduler.rank(runtime, task)
        for score in ranking.eligible:
            if not self.quarantine.is_quarantined(score.worker_id):
                return DispatchDecision(True, score.worker_id, "eligible worker selected")
        return DispatchDecision(False, None, "no healthy eligible worker")
    def record_success(self, worker_id: str) -> None:
        self.scheduler.record_success(worker_id)
    def record_failure(self, worker_id: str) -> None:
        self.scheduler.record_failure(worker_id)
    def quarantine_worker(self, worker_id: str, *, reason: str, seconds: float | None = None) -> None:
        self.quarantine.quarantine(worker_id, reason=reason, seconds=seconds)
    def release_worker(self, worker_id: str) -> bool:
        return self.quarantine.release(worker_id)
    def status(self) -> dict[str, object]:
        return {"quarantine": [asdict(item) for item in self.quarantine.records()], "circuits": self.scheduler.breaker.snapshot()}

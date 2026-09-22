"""High-level resilience supervisor combining quarantine, circuits and load shedding."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from skeleton.agents.swarm_load_shed import LoadShedPolicy, ShedDecision
from skeleton.agents.swarm_quarantine import QuarantineController
from skeleton.agents.swarm_resilient_scheduler import ResilientSwarmScheduler
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask, WorkerState

@dataclass(frozen=True, slots=True)
class DispatchDecision:
    accepted: bool
    worker_id: str | None
    reason: str

class SwarmSupervisor:
    def __init__(self, *, shed_policy: LoadShedPolicy | None = None) -> None:
        self.shed_policy = shed_policy or LoadShedPolicy()
        self.quarantine = QuarantineController()
        self.scheduler = ResilientSwarmScheduler()
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

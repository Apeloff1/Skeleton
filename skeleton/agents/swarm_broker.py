"""Unified bounded submission and dispatch broker for production swarm execution."""
from __future__ import annotations
from dataclasses import dataclass
from skeleton.agents.swarm_control import SubmitResult, SwarmControlPlane
from skeleton.agents.swarm_runtime import AdmissionError, LeaseError, SwarmRuntime, SwarmTask
from skeleton.agents.swarm_supervisor import DispatchDecision, SwarmSupervisor

@dataclass(frozen=True, slots=True)
class BrokerResult:
    task_id: str
    submitted: bool
    duplicate: bool
    worker_id: str | None
    leased: bool
    reason: str

class SwarmBroker:
    def __init__(self, runtime: SwarmRuntime, *, control: SwarmControlPlane | None = None, supervisor: SwarmSupervisor | None = None) -> None:
        self.runtime=runtime; self.control=control or SwarmControlPlane(runtime); self.supervisor=supervisor or SwarmSupervisor()
    def submit_and_dispatch(self, task: SwarmTask, *, idempotency_key: str | None = None) -> BrokerResult:
        result=self.control.submit(task, idempotency_key=idempotency_key)
        resident=result.task
        decision=self.supervisor.dispatch(self.runtime, resident)
        if not decision.accepted or decision.worker_id is None:
            return BrokerResult(resident.id, True, result.duplicate, None, False, decision.reason)
        leased=self.runtime.lease(decision.worker_id, limit=1)
        selected=next((item for item in leased if item.id == resident.id), None)
        if selected is None:
            return BrokerResult(resident.id, True, result.duplicate, decision.worker_id, False, "worker lease selected different queued task")
        return BrokerResult(resident.id, True, result.duplicate, decision.worker_id, True, "submitted and leased")
    def record_success(self, worker_id: str, task_id: str):
        task=self.runtime.succeed(worker_id, task_id); self.supervisor.record_success(worker_id); return task
    def record_failure(self, worker_id: str, task_id: str, error: str):
        task=self.runtime.fail(worker_id, task_id, error); self.supervisor.record_failure(worker_id); return task

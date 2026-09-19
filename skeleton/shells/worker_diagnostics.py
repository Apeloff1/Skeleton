"""Cross-component consistency diagnostics for worker-plane state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.queue import QueueState,ShellWorkQueue
from skeleton.shells.worker_heartbeat import HeartbeatRegistry,WorkerLiveness
from skeleton.shells.worker_identity import WorkerRegistry
from skeleton.shells.worker_supervisor import SupervisionState,WorkerSupervisor


class DiagnosticSeverity(str,Enum):
    INFO="info"
    WARNING="warning"
    ERROR="error"


@dataclass(frozen=True)
class WorkerDiagnostic:
    severity:DiagnosticSeverity
    code:str
    message:str
    worker_id:str=""
    item_id:str=""

    def to_dict(self)->dict[str,str]:
        return {
            "severity":self.severity.value,
            "code":self.code,
            "message":self.message,
            "worker_id":self.worker_id,
            "item_id":self.item_id,
        }


@dataclass(frozen=True)
class WorkerDiagnosticsReport:
    findings:tuple[WorkerDiagnostic,...]

    @property
    def errors(self)->int:
        return sum(item.severity is DiagnosticSeverity.ERROR for item in self.findings)

    @property
    def warnings(self)->int:
        return sum(item.severity is DiagnosticSeverity.WARNING for item in self.findings)

    @property
    def ok(self)->bool:return self.errors==0

    def to_dict(self)->dict[str,object]:
        return {
            "ok":self.ok,
            "errors":self.errors,
            "warnings":self.warnings,
            "findings":[item.to_dict() for item in self.findings],
        }


class WorkerDiagnostics:
    def __init__(
        self,
        *,
        workers:WorkerRegistry,
        heartbeats:HeartbeatRegistry,
        queue:ShellWorkQueue,
        supervisor:WorkerSupervisor|None=None,
    )->None:
        self.workers=workers
        self.heartbeats=heartbeats
        self.queue=queue
        self.supervisor=supervisor

    def inspect(self)->WorkerDiagnosticsReport:
        findings:list[WorkerDiagnostic]=[]
        registrations={item.identity.worker_id:item for item in self.workers.snapshot().registrations}

        for worker_id,registration in registrations.items():
            identity=registration.identity
            live=self.heartbeats.liveness(identity)
            if registration.enabled and live.liveness is WorkerLiveness.STALE:
                findings.append(WorkerDiagnostic(
                    DiagnosticSeverity.ERROR,"enabled_stale_worker",
                    "enabled worker has a stale heartbeat",worker_id=worker_id,
                ))
            if not registration.enabled and live.liveness is WorkerLiveness.HEALTHY:
                findings.append(WorkerDiagnostic(
                    DiagnosticSeverity.INFO,"disabled_healthy_worker",
                    "disabled worker continues to heartbeat",worker_id=worker_id,
                ))
            if self.supervisor is not None:
                supervised=self.supervisor.get(worker_id)
                if supervised is not None:
                    if supervised.state is SupervisionState.QUARANTINED and registration.enabled:
                        findings.append(WorkerDiagnostic(
                            DiagnosticSeverity.ERROR,"quarantine_enabled_mismatch",
                            "quarantined worker is still enabled",worker_id=worker_id,
                        ))
                    if supervised.identity.generation!=identity.generation:
                        findings.append(WorkerDiagnostic(
                            DiagnosticSeverity.ERROR,"supervisor_generation_mismatch",
                            "supervisor tracks a different worker generation",worker_id=worker_id,
                        ))

        for item in self.queue.claimed():
            if not item.owner:
                findings.append(WorkerDiagnostic(
                    DiagnosticSeverity.ERROR,"ownerless_claim","claimed queue item has no owner",item_id=item.item_id
                ))
                continue
            registration=registrations.get(item.owner)
            if registration is None:
                findings.append(WorkerDiagnostic(
                    DiagnosticSeverity.WARNING,"claim_owner_unregistered",
                    "queue claim owner is not registered",worker_id=item.owner,item_id=item.item_id,
                ))
            elif not registration.enabled:
                findings.append(WorkerDiagnostic(
                    DiagnosticSeverity.WARNING,"claim_owner_disabled",
                    "queue item is held by a disabled worker",worker_id=item.owner,item_id=item.item_id,
                ))

        counts=self.queue.counts()
        if counts.get("claimed",0)>0 and not registrations:
            findings.append(WorkerDiagnostic(
                DiagnosticSeverity.ERROR,"claims_without_workers",
                "queue has claimed items but worker registry is empty",
            ))
        return WorkerDiagnosticsReport(tuple(findings))

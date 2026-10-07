"""Composition root for the extended worker execution plane."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable,Mapping

from skeleton.shells.queue import ShellWorkQueue
from skeleton.shells.worker_admission import WorkerAdmission,WorkerAdmissionDecision
from skeleton.shells.worker_affinity import JobRequirements,WorkerPlacement
from skeleton.shells.worker_backpressure import BackpressureController,BackpressureDecision
from skeleton.shells.worker_capacity import CapacityDemand,WorkerCapacityCatalog
from skeleton.shells.worker_checkpoint import CheckpointChain
from skeleton.shells.worker_failover import WorkerFailover
from skeleton.shells.worker_heartbeat import HeartbeatRegistry,LivenessView
from skeleton.shells.worker_health import WorkerHealthInspector,WorkerHealthReport
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRegistration,WorkerRegistry
from skeleton.shells.worker_journal import WorkerJournal
from skeleton.shells.worker_metrics import WorkerMetrics
from skeleton.shells.worker_quota import WorkerQuotaLedger
from skeleton.shells.worker_recovery import RecoveryReport,WorkerRecoveryCoordinator
from skeleton.shells.worker_supervisor import WorkerSupervisor


@dataclass(frozen=True)
class WorkerRuntimeSnapshot:
    workers:int
    enabled:int
    healthy:int
    late:int
    stale:int
    queued:int
    claimed:int
    journal_events:int
    journal_head:str

    def to_dict(self)->dict[str,object]:
        return {
            "workers":self.workers,
            "enabled":self.enabled,
            "healthy":self.healthy,
            "late":self.late,
            "stale":self.stale,
            "queued":self.queued,
            "claimed":self.claimed,
            "journal_events":self.journal_events,
            "journal_head":self.journal_head,
        }


class WorkerRuntime:
    """Own the worker control objects without introducing hidden execution."""

    def __init__(
        self,
        *,
        queue:ShellWorkQueue|None=None,
        workers:WorkerRegistry|None=None,
        heartbeats:HeartbeatRegistry|None=None,
        quotas:WorkerQuotaLedger|None=None,
        capacities:WorkerCapacityCatalog|None=None,
        backpressure:BackpressureController|None=None,
        journal:WorkerJournal|None=None,
        metrics:WorkerMetrics|None=None,
        clock:Callable[[],float]=time.monotonic,
    )->None:
        self.clock=clock
        self.queue=queue or ShellWorkQueue()
        self.workers=workers or WorkerRegistry(clock=clock)
        self.heartbeats=heartbeats or HeartbeatRegistry(workers=self.workers,clock=clock)
        self.quotas=quotas or WorkerQuotaLedger(clock=clock)
        self.capacities=capacities or WorkerCapacityCatalog()
        self.backpressure=backpressure or BackpressureController(clock=clock)
        self.journal=journal or WorkerJournal(clock=clock)
        self.metrics=metrics or WorkerMetrics()
        self.supervisor=WorkerSupervisor(self.workers,clock=clock)
        self.placement=WorkerPlacement()
        self.admission=WorkerAdmission(
            placement=self.placement,
            quotas=self.quotas,
            capacities=self.capacities,
        )
        self.health=WorkerHealthInspector(
            workers=self.workers,
            heartbeats=self.heartbeats,
            queue=self.queue,
            supervisor=self.supervisor,
        )
        self.failover=WorkerFailover(self.workers,self.heartbeats,clock=clock)
        self._checkpoints:dict[str,CheckpointChain]={}

    def register(self,identity:WorkerIdentity,*,metadata:Mapping[str,str]|None=None)->WorkerRegistration:
        registration=self.workers.register(identity,metadata=metadata)
        self.supervisor.attach(identity)
        self.journal.append(
            worker_id=identity.worker_id,
            generation=identity.generation,
            kind="worker.registered",
            detail={"role":identity.role.value},
        )
        self._checkpoints[identity.worker_id]=CheckpointChain(identity.worker_id,identity.generation)
        return registration

    def replace(self,identity:WorkerIdentity,*,metadata:Mapping[str,str]|None=None)->WorkerRegistration:
        registration=self.workers.replace(identity,metadata=metadata)
        self.supervisor.attach(identity)
        self.journal.append(
            worker_id=identity.worker_id,
            generation=identity.generation,
            kind="worker.replaced",
        )
        self._checkpoints[identity.worker_id]=CheckpointChain(identity.worker_id,identity.generation)
        return registration

    def heartbeat(
        self,
        identity:WorkerIdentity,
        *,
        sequence:int,
        metrics:Mapping[str,float]|None=None,
        busy:bool=False,
        inflight:int=0,
    ):
        beat=self.heartbeats.beat(identity,sequence=sequence,metrics=metrics,busy=busy,inflight=inflight)
        self.journal.append(
            worker_id=identity.worker_id,
            generation=identity.generation,
            kind="worker.heartbeat",
            detail={"sequence":sequence,"busy":bool(busy),"inflight":inflight},
        )
        return beat

    def liveness_map(self)->dict[str,LivenessView]:
        return {
            registration.identity.worker_id:self.heartbeats.liveness(registration.identity)
            for registration in self.workers.snapshot().registrations
        }

    def inspect_admission(
        self,
        *,
        principal:str,
        requirements:JobRequirements|None=None,
        demand:CapacityDemand|None=None,
        backpressure:BackpressureDecision|None=None,
    )->WorkerAdmissionDecision:
        return self.admission.inspect(
            principal=principal,
            registrations=self.workers.snapshot().registrations,
            liveness=self.liveness_map(),
            requirements=requirements,
            demand=demand,
            backpressure=backpressure,
        )

    def checkpoint(self,identity:WorkerIdentity,*,claim_ids:tuple[str,...]=()):
        self.workers.require_current(identity)
        chain=self._checkpoints.get(identity.worker_id)
        if chain is None or chain.generation!=identity.generation:
            chain=CheckpointChain(identity.worker_id,identity.generation)
            self._checkpoints[identity.worker_id]=chain
        checkpoint=chain.append(queue_claim_ids=claim_ids)
        self.journal.append(
            worker_id=identity.worker_id,
            generation=identity.generation,
            kind="worker.checkpoint",
            detail={"sequence":checkpoint.sequence},
        )
        return checkpoint

    def recover(self,coordinator:WorkerRecoveryCoordinator)->RecoveryReport:
        report=coordinator.recover()
        for recovery in report.recoveries:
            self.journal.append(
                worker_id=recovery.identity.worker_id,
                generation=recovery.identity.generation,
                kind="worker.recovered",
                detail={"items":len(recovery.claimed_items)},
            )
            if recovery.claimed_items:
                self.metrics.recovered(recovery.identity.worker_id,len(recovery.claimed_items))
        return report

    def health_report(self)->WorkerHealthReport:
        return self.health.inspect()

    def snapshot(self)->WorkerRuntimeSnapshot:
        registry=self.workers.snapshot()
        heartbeat=self.heartbeats.snapshot()
        counts=self.queue.counts()
        return WorkerRuntimeSnapshot(
            workers=len(registry.registrations),
            enabled=registry.enabled,
            healthy=heartbeat.healthy,
            late=heartbeat.late,
            stale=heartbeat.stale,
            queued=counts.get("queued",0),
            claimed=counts.get("claimed",0),
            journal_events=len(self.journal),
            journal_head=self.journal.head_digest,
        )

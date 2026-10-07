"""Operator-facing worker service composed from pure control-plane primitives."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable,Mapping

from skeleton.shells.worker_controller import SubmissionDecision,WorkerController,WorkerSubmission
from skeleton.shells.worker_diagnostics import WorkerDiagnostics,WorkerDiagnosticsReport
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRegistration
from skeleton.shells.worker_recovery import RecoveryPolicy,RecoveryReport,WorkerRecoveryCoordinator
from skeleton.shells.worker_runtime import WorkerRuntime
from skeleton.shells.worker_snapshot import FleetSnapshot,FleetSnapshotter


@dataclass(frozen=True)
class WorkerServiceStatus:
    runtime:dict[str,object]
    health:dict[str,object]
    diagnostics:dict[str,object]
    snapshot_digest:str

    def to_dict(self)->dict[str,object]:
        return {
            "runtime":dict(self.runtime),
            "health":dict(self.health),
            "diagnostics":dict(self.diagnostics),
            "snapshot_digest":self.snapshot_digest,
        }


class WorkerService:
    """High-level facade that still performs no hidden background execution."""

    def __init__(
        self,
        runtime:WorkerRuntime|None=None,
        *,
        clock:Callable[[],float]=time.monotonic,
    )->None:
        self.runtime=runtime or WorkerRuntime(clock=clock)
        self.controller=WorkerController(self.runtime,clock=clock)
        self.recovery=WorkerRecoveryCoordinator(
            workers=self.runtime.workers,
            heartbeats=self.runtime.heartbeats,
            queue=self.runtime.queue,
            policy=RecoveryPolicy(),
            clock=clock,
        )
        self.diagnostics=WorkerDiagnostics(
            workers=self.runtime.workers,
            heartbeats=self.runtime.heartbeats,
            queue=self.runtime.queue,
            supervisor=self.runtime.supervisor,
        )
        self.snapshotter=FleetSnapshotter(
            workers=self.runtime.workers,
            heartbeats=self.runtime.heartbeats,
            queue=self.runtime.queue,
            metrics=self.runtime.metrics,
            health=self.runtime.health,
            supervisor=self.runtime.supervisor,
            clock=clock,
        )

    def register(
        self,
        identity:WorkerIdentity,
        *,
        metadata:Mapping[str,str]|None=None,
    )->WorkerRegistration:
        return self.runtime.register(identity,metadata=metadata)

    def heartbeat(self,identity:WorkerIdentity,*,sequence:int,**kwargs):
        return self.runtime.heartbeat(identity,sequence=sequence,**kwargs)

    def submit(self,submission:WorkerSubmission,**kwargs)->SubmissionDecision:
        return self.controller.submit(submission,**kwargs)

    def recover(self)->RecoveryReport:
        return self.runtime.recover(self.recovery)

    def diagnostics_report(self)->WorkerDiagnosticsReport:
        return self.diagnostics.inspect()

    def snapshot(self)->FleetSnapshot:
        return self.snapshotter.capture()

    def status(self)->WorkerServiceStatus:
        snapshot=self.snapshot()
        return WorkerServiceStatus(
            runtime=self.runtime.snapshot().to_dict(),
            health=self.runtime.health_report().to_dict(),
            diagnostics=self.diagnostics_report().to_dict(),
            snapshot_digest=snapshot.digest,
        )

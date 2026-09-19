"""Managed QueueWorker wrapper with quota, metrics, journal, and event custody."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from skeleton.shells.worker import QueueWorker,WorkResult
from skeleton.shells.worker_events import WorkerEvents
from skeleton.shells.worker_journal import WorkerJournal
from skeleton.shells.worker_metrics import WorkerMetrics
from skeleton.shells.worker_quota import QuotaReservation,WorkerQuotaLedger


PrincipalResolver=Callable[[object],str]


def _default_principal(_item)->str:return "default"


@dataclass(frozen=True)
class ManagedWorkResult:
    result:WorkResult|None
    principal:str
    quota_reserved:bool
    metric_recorded:bool

    @property
    def ok(self)->bool:
        return self.result is not None and self.result.ok


class ManagedQueueWorker:
    """Add control-plane custody around an existing QueueWorker.

    QueueWorker remains the component that claims and executes. This wrapper
    performs admission-side quota reservation before delegating and records
    low-cardinality evidence afterward.
    """

    def __init__(
        self,
        worker:QueueWorker,
        *,
        quotas:WorkerQuotaLedger|None=None,
        metrics:WorkerMetrics|None=None,
        journal:WorkerJournal|None=None,
        events:WorkerEvents|None=None,
        principal_resolver:PrincipalResolver|None=None,
    )->None:
        self.worker=worker
        self.quotas=quotas
        self.metrics=metrics or WorkerMetrics()
        self.journal=journal or WorkerJournal()
        self.events=events or WorkerEvents()
        self.principal_resolver=principal_resolver or _default_principal

    def run_once(self)->ManagedWorkResult:
        # We cannot reserve quota before QueueWorker claims without duplicating
        # its ownership logic. Instead inspect the next queued principal through
        # a resolver based on the worker identity, then use a reservation for the
        # execution attempt. Queue limits remain the authoritative ownership gate.
        principal=self.principal_resolver(self.worker)
        reservation:QuotaReservation|None=None
        if self.quotas is not None:
            reservation=self.quotas.reserve(principal)

        self.metrics.started(self.worker.owner)
        self.events.emit("worker.execution.started",worker_id=self.worker.owner,data={"principal":principal})
        self.journal.append(
            worker_id=self.worker.owner,generation=1,kind="worker.execution.started",
            detail={"principal":principal},
        )

        try:
            result=self.worker.run_once()
        except Exception as exc:
            if reservation is not None:
                self.quotas.complete(reservation,ok=False)
            self.metrics.completed(self.worker.owner,ok=False,duration_ms=0,output_bytes=0)
            self.events.emit("worker.execution.error",worker_id=self.worker.owner,data={"error_type":type(exc).__name__})
            self.journal.append(
                worker_id=self.worker.owner,generation=1,kind="worker.execution.error",
                detail={"error_type":type(exc).__name__},
            )
            raise

        if result is None:
            if reservation is not None:self.quotas.release(reservation)
            return ManagedWorkResult(None,principal,reservation is not None,False)

        ok=result.ok
        if reservation is not None:
            self.quotas.complete(reservation,ok=ok)
        self.metrics.completed(self.worker.owner,ok=ok,duration_ms=0,output_bytes=0)
        self.events.emit(
            "worker.execution.completed",worker_id=self.worker.owner,
            data={"principal":principal,"ok":ok,"item_id":result.item_id},
        )
        self.journal.append(
            worker_id=self.worker.owner,generation=1,kind="worker.execution.completed",
            detail={"principal":principal,"ok":ok,"item_id":result.item_id},
        )
        return ManagedWorkResult(result,principal,reservation is not None,True)

    def drain(self,*,max_items:int=100)->tuple[ManagedWorkResult,...]:
        if max_items<=0:raise ValueError("max_items must be positive")
        results=[]
        for _ in range(max_items):
            result=self.run_once()
            if result.result is None:break
            results.append(result)
        return tuple(results)

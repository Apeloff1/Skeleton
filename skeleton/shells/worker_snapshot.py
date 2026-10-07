"""Canonical fleet snapshots for diagnostics, handoff, and audit."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from typing import Callable

from skeleton.shells.queue import ShellWorkQueue
from skeleton.shells.worker_heartbeat import HeartbeatRegistry
from skeleton.shells.worker_health import WorkerHealthInspector
from skeleton.shells.worker_identity import WorkerRegistry
from skeleton.shells.worker_metrics import WorkerMetrics
from skeleton.shells.worker_supervisor import WorkerSupervisor


@dataclass(frozen=True)
class FleetSnapshot:
    schema_version:int
    created_at:float
    workers:tuple[dict[str,object],...]
    heartbeats:dict[str,object]
    queue:dict[str,int]
    metrics:dict[str,object]
    health:dict[str,object]
    supervision:tuple[dict[str,object],...]

    def __post_init__(self)->None:
        if self.schema_version<=0:raise ValueError("schema_version must be positive")
        if self.created_at<0:raise ValueError("created_at may not be negative")

    def to_dict(self)->dict[str,object]:
        return {
            "schema_version":self.schema_version,
            "created_at":self.created_at,
            "workers":list(self.workers),
            "heartbeats":dict(self.heartbeats),
            "queue":dict(self.queue),
            "metrics":dict(self.metrics),
            "health":dict(self.health),
            "supervision":list(self.supervision),
        }

    @property
    def digest(self)->str:
        payload=json.dumps(self.to_dict(),sort_keys=True,separators=(",",":"),ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def dumps(self)->str:
        return json.dumps(self.to_dict(),sort_keys=True,separators=(",",":"),ensure_ascii=False)


class FleetSnapshotter:
    def __init__(
        self,
        *,
        workers:WorkerRegistry,
        heartbeats:HeartbeatRegistry,
        queue:ShellWorkQueue,
        metrics:WorkerMetrics,
        health:WorkerHealthInspector,
        supervisor:WorkerSupervisor,
        clock:Callable[[],float]=time.monotonic,
    )->None:
        self.workers=workers
        self.heartbeats=heartbeats
        self.queue=queue
        self.metrics=metrics
        self.health=health
        self.supervisor=supervisor
        self._clock=clock

    def capture(self)->FleetSnapshot:
        registry=self.workers.snapshot()
        heartbeat=self.heartbeats.snapshot()
        return FleetSnapshot(
            schema_version=1,
            created_at=self._clock(),
            workers=tuple(item.to_dict() for item in registry.registrations),
            heartbeats=heartbeat.to_dict(),
            queue=self.queue.counts(),
            metrics=self.metrics.snapshot().to_dict(),
            health=self.health.inspect().to_dict(),
            supervision=tuple(item.to_dict() for item in self.supervisor.snapshot()),
        )

    @staticmethod
    def loads(raw:str)->dict[str,object]:
        payload=json.loads(raw)
        if not isinstance(payload,dict):raise ValueError("fleet snapshot must be an object")
        if payload.get("schema_version")!=1:raise ValueError("unsupported fleet snapshot version")
        required={"created_at","workers","heartbeats","queue","metrics","health","supervision"}
        if not required<=set(payload):raise ValueError("fleet snapshot is incomplete")
        return payload

"""Lease-bound runtime receipt commit boundary."""
from __future__ import annotations
from dataclasses import dataclass

from .dragon_analysis_runtime import DragonAnalysisRuntime,RunCheckpoint
from .dragon_analysis_chains import LayerReceipt
from .dragon_worker_leases import DragonWorkerLeases,WorkerLease
from .dragon_runtime_events import DragonRuntimeEventLedger

@dataclass(frozen=True)
class LeasedCommit:
 checkpoint:RunCheckpoint
 worker_id:str
 implementation:str
 version:str
 generation:int

def commit_leased_receipt(runtime:DragonAnalysisRuntime,leases:DragonWorkerLeases,
    lease:WorkerLease,receipt:LayerReceipt,*,now:float,expected_revision:int,
    authorized:bool)->LeasedCommit:
 if not authorized: raise PermissionError("leased receipt commit requires authorization")
 if receipt.layer.value!=lease.layer: raise ValueError("lease layer does not match receipt")
 leases.require(lease,now=now,authorized=True)
 cp=runtime.commit_receipt(lease.owner,lease.run_id,receipt,now=now,
   expected_revision=expected_revision,authorized=True)
 DragonRuntimeEventLedger(runtime.db).append(lease.owner,lease.run_id,event_type="worker_receipt",
   layer=lease.layer,outcome="accepted",evidence_fingerprint=receipt.output_fingerprint,
   error_code="",occurred_at=now,authorized=True)
 leases.release(lease,now=now,authorized=True)
 return LeasedCommit(cp,lease.worker_id,lease.implementation,lease.version,lease.generation)
